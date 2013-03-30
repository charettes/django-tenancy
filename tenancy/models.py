from __future__ import unicode_literals
from collections import namedtuple
import copy
import copy_reg
from contextlib import contextmanager

import django
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DEFAULT_DB_ALIAS, models
from django.db.models.base import ModelBase
from django.db.models.fields.related import (add_lazy_relation,
    RECURSIVE_RELATIONSHIP_CONSTANT)
from django.db.models.loading import get_model
from django.utils.datastructures import SortedDict

from . import get_tenant_model
from .utils import (clear_opts_related_cache, model_name_from_opts,
    remove_from_app_cache)


class AbstractTenant(models.Model):
    class Meta:
        abstract = True

    @contextmanager
    def as_global(self):
        """
        Expose this tenant as thread local object. This is required by parts
        of django relying on global states such as authentification backends.
        """
        connection = connections[DEFAULT_DB_ALIAS]
        try:
            connection.tenant = self
            yield
        finally:
            del connection.tenant

    @property
    def model_name_prefix(self):
        return "Tenant_%s" % '_'.join(self.natural_key())

    @property
    def db_schema(self):
        return "tenant_%s" % '_'.join(self.natural_key())

    def natural_key(self):
        raise NotImplementedError


class Tenant(AbstractTenant):
    name = models.CharField(unique=True, max_length=20)

    class Meta:
        if django.VERSION >= (1, 5):  #pragma: no cover
            swappable = 'TENANCY_TENANT_MODEL'

    def natural_key(self):
        return (self.name,)


TenantOptions = namedtuple(
    'TenantOptions',
    ('model_name',  'related_name', 'model')
)


def meta(Meta=None, **opts):
    """
    Create a class with specified opts as attributes to be used as model
    definition options.
    """
    if Meta:
        opts = dict(Meta.__dict__, **opts)
    return type(str('Meta'), (), opts)


def db_schema_table(tenant, db_table):
    connection = connections[tenant._state.db]
    if connection.vendor == 'postgresql':  #pragma: no cover
        # See https://code.djangoproject.com/ticket/6148#comment:47
        return '%s\".\"%s' % (tenant.db_schema, db_table)
    else:  #pragma: no cover
        return "%s_%s" % (tenant.db_schema, db_table)


class Reference(object):
    __slots__ = ('model', 'bases', 'attrs', 'Meta')

    def __init__(self, model, bases, attrs, Meta):
        self.model = model
        self.bases = bases
        self.attrs = attrs
        self.Meta = Meta

    def object_name_for_tenant(self, tenant):
        return "%s_%s" % (
            tenant.model_name_prefix,
            self.model._meta.object_name
        )

    def for_tenant(self, tenant):
        app_label = self.model._meta.app_label
        object_name = self.object_name_for_tenant(tenant)
        return "%s.%s" % (app_label, object_name)


class TenantModelBase(ModelBase):
    references = SortedDict()
    tenant_model_class = None

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        Meta = attrs.setdefault('Meta', meta())
        if (getattr(Meta, 'abstract', False) or
            any(isinstance(base, cls) and base._meta.managed and
                not base._meta.abstract for base in bases)):
            # Abstract model definition and ones subclassing tenant specific
            # ones shouldn't get any special treatment.
            model = super_new(cls, name, bases, attrs)
            if not cls.tenant_model_class:
                cls.tenant_model_class = model
        elif getattr(Meta, 'proxy', False):
            raise NotImplementedError(
                "Tenant model proxies haven't been implemented yet"
            )
        else:
            # Extract the specified related name if it exists.
            try:
                related_name = attrs.pop('TenantMeta').related_name
            except (KeyError, AttributeError):
                related_name = name.lower() + 's'
            # Create an intermediary abstract model to validate related fields
            # and assign a tenant specific intermediary model to m2m fields.
            # This is needed because creating the concrete model automatically
            # interpolate the `related_name` and create and intermediary model
            # if None is specified using the `through` argument. This is really
            # just a original field definition reference.
            base = super_new(
                cls, str("Abstract%s" % name), bases,
                dict(attrs, Meta=meta(Meta, abstract=True))
            )
            opts = base._meta
            model = super_new(cls, name, (base,), {
                '__module__': base.__module__,
                'Meta': meta(Meta, managed=False)}
            )
            reference = Reference(model, bases, attrs, Meta)
            cls.references[model] = reference
            for field in opts.local_fields:
                if field.rel:
                    cls.validate_related_name(field, field.rel.to, model)
            for m2m in opts.local_many_to_many:
                cls.validate_related_name(m2m, m2m.rel.to, model)
                if not m2m.rel.through:
                    m2m.rel.through = cls.intermediary_model_factory(m2m, reference)
                    # Set the automatically created intermediary model of the
                    # to un-managed mode since it's really just a facade.
                    model._meta.get_field(m2m.name).rel.through._meta.managed = False
                else:
                    cls.validate_through(m2m, m2m.rel.to, model)
            model._tenant_meta = TenantOptions(name, related_name, model)
            # Attach a descriptor to the tenant model to access the underlying
            # model based on the tenant instance.
            tenant_model = get_tenant_model(model._meta.app_label)
            setattr(tenant_model, related_name, TenantModelDescriptor(model))
        return model

    @classmethod
    def validate_related_name(cls, field, rel_to, model):
        """
        Make sure that related fields pointing to non-tenant models specify
        a related name containing a %(class)s format placeholder.
        """
        if isinstance(rel_to, basestring):
            add_lazy_relation(model, field, rel_to, cls.validate_related_name)
        elif not isinstance(rel_to, cls):
            related_name = field.rel.related_name
            if (related_name is not None and
                not (field.rel.is_hidden() or '%(class)s' in related_name)):
                    del cls.references[model]
                    remove_from_app_cache(model)
                    raise ImproperlyConfigured(
                        "Since `%s.%s` is originating from an instance "
                        "of `TenantModelBase` and not pointing to one "
                        "its `related_name` option must ends with a "
                        "'+' or contain the '%%(class)s' format "
                        "placeholder." % (model.__name__, field.name)
                    )

    @classmethod
    def validate_through(cls, field, rel_to, model):
        """
        Make sure the related fields with a specified through points to an
        instance of `TenantModelBase`.
        """
        through = field.rel.through
        if isinstance(through, basestring):
            add_lazy_relation(model, field, through, cls.validate_through)
        elif not isinstance(through, cls):
            del cls.references[model]
            remove_from_app_cache(model)
            raise ImproperlyConfigured(
                "Since `%s.%s` is originating from an instance of "
                "`TenantModelBase` its `through` option must also be pointing "
                "to one." % (model.__name__, field.name)
            )

    @classmethod
    def intermediary_model_factory(cls, field, reference):
        from_model = reference.model
        to_model = field.rel.to
        opts = from_model._meta
        from_model_name = model_name_from_opts(opts)
        if to_model == RECURSIVE_RELATIONSHIP_CONSTANT:
            from_ = "from_%s" % from_model_name
            to = "to_%s" % from_model_name
            to_model = from_model
        else:
            from_ = from_model_name
            if isinstance(to_model, basestring):
                to = to_model.split('.')[-1].lower()
            else:
                to = model_name_from_opts(to_model._meta)
        Meta = meta(
            db_table=field._get_m2m_db_table(opts),
            auto_created=reference.model,
            app_label=opts.app_label,
            db_tablespace=opts.db_tablespace,
            unique_together=(from_, to),
            verbose_name="%(from)s-%(to)s relationship" % {'from': from_, 'to': to},
            verbose_name_plural="%(from)s-%(to)s relationships" % {'from': from_, 'to': to}
        )
        # TODO: Add support for db_constraints
        name = str("Tenant_%s_%s" % (opts.object_name, field.name))
        return type(name, (cls.tenant_model_class,), {
            'Meta': Meta,
            '__module__': reference.model.__module__,
            from_: models.ForeignKey(
                from_model, related_name="%s+" % name,
                db_tablespace=field.db_tablespace
            ),
            to: models.ForeignKey(
                to_model, related_name="%s+" % name,
                db_tablespace=field.db_tablespace
            ),
        })

    def abstract_tenant_model_factory(self, tenant):
        cls = self.__class__
        reference = cls.references[self]
        model = super(TenantModelBase, self).__new__(cls,
            str("Abstract%s" % str(reference.object_name_for_tenant(tenant))),
            tuple(
                base.for_tenant(tenant) if isinstance(base, cls)
                    and not base._meta.abstract
                else base for base in reference.bases
            ),
            dict(
                 reference.attrs,
                 Meta=meta(reference.Meta, abstract=True),
                 tenant=tenant,
                 _tenant_meta=self._tenant_meta
            )
        )
        opts = model._meta
        # Replace related fields pointing to tenant models by their correct
        # tenant specific class.
        local_related_fields = [
            field for field in opts.local_fields if field.rel
        ] + opts.local_many_to_many
        tenant_model_name_prefix = "%s_" % tenant.model_name_prefix.lower()
        for related_field in local_related_fields:
            field = copy.deepcopy(related_field)
            rel = field.rel
            to = rel.to
            if getattr(rel, 'parent_link', False):
                field.name = field.name.replace(tenant_model_name_prefix, '')
                opts.parents[to] = field
            elif isinstance(to, cls):
                rel.to = cls.references[to].for_tenant(tenant)
            elif to != RECURSIVE_RELATIONSHIP_CONSTANT:
                related_name = rel.related_name
                if not related_name:
                    # Hide reverse relationships with unspecified related name
                    related_name = 'unspecified_for_tenant_model+'
                rel.related_name = related_name
                clear_opts_related_cache(to)
            if isinstance(field, models.ManyToManyField):
                through = field.rel.through
                rel.through = cls.references[through].for_tenant(tenant)
                opts.local_many_to_many.remove(related_field)
            else:
                opts.local_fields.remove(related_field)
            field.contribute_to_class(model, field.name)
        return model

    def for_tenant(self, tenant):
        """
        Returns the model for the specific tenant.
        """
        cls = self.__class__
        reference = cls.references[self]
        opts = self._meta
        object_name = reference.object_name_for_tenant(tenant)
        # Return the already cached model instead of creating a new one.
        tenant_model = get_model(opts.app_label, object_name.lower())
        if tenant_model:
            return tenant_model
        # Create an abstract base to replace related fields with
        # relationships pointing to tenant models with their correct
        # tenant specific equivalent.
        return super(TenantModelBase, self).__new__(cls,
            str(object_name),
            (self.abstract_tenant_model_factory(tenant),),
            {
                '__module__': self.__module__,
                'Meta': meta(
                    reference.Meta,
                    # TODO: Use `db_schema` once django #6148 is fixed.
                    db_table=db_schema_table(tenant, opts.db_table)
                )
            }
        )

    def __instancecheck__(self, instance):
        return self.__subclasscheck__(instance.__class__)

    def __subclasscheck__(self, subclass):
        if isinstance(subclass, TenantModelBase):
            if (getattr(self, '_tenant_meta', None) is
                getattr(subclass, '_tenant_meta', None)):
                return True
            return any(self.__subclasscheck__(b) for b in subclass.__bases__)


def __unpickle_tenant_model_base(model, tenant_pk):
    tenant = get_tenant_model()._default_manager.get(pk=tenant_pk)
    return model.for_tenant(tenant)


def __pickle_tenant_model_base(model):
    if hasattr(model, 'tenant'):
        return (
            __unpickle_tenant_model_base,
            (model._tenant_meta.model, model.tenant.pk)
        )
    return model.__name__

copy_reg.pickle(TenantModelBase, __pickle_tenant_model_base)


class TenantModelDescriptor(object):
    __slots__ = ('model',)

    def __init__(self, model):
        self.model = model

    def __get__(self, tenant, owner):
        if not tenant:
            return self
        return self.model.for_tenant(tenant)._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True
