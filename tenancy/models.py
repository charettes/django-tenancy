from __future__ import unicode_literals
from collections import namedtuple
import copy

import django
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, models
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


def meta(**opts):
    """
    Create a class with specified opts as attributes to be used as model
    definition options.
    """
    return type(str('Meta'), (), opts)


def db_schema_table(tenant, db_table):
    connection = connections[tenant._state.db]
    if connection.vendor == 'postgresql':  #pragma: no cover
        # See https://code.djangoproject.com/ticket/6148#comment:47
        return '%s\".\"%s' % (tenant.db_schema, db_table)
    else:  #pragma: no cover
        return "%s_%s" % (tenant.db_schema, db_table)


class Reference(object):
    __slots__ = ('related_name', 'model')

    def __init__(self, related_name, model):
        self.related_name = related_name
        self.model = model

    def object_name_for_tenant(self, tenant):
        return "%s_%s" % (
            tenant.model_name_prefix,
            self.model._meta.object_name
        )

    def model_for_tenant(self, tenant, identifier=False):
        app_label = self.model._meta.app_label
        object_name = self.object_name_for_tenant(tenant)
        model = get_model(app_label, object_name.lower(), only_installed=False)
        if model:
            return model
        elif identifier:
            return "%s.%s" % (app_label, object_name)


class TenantModelBase(ModelBase):
    references = SortedDict()
    tenant_model_class = None

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        Meta = attrs.setdefault('Meta', meta())
        if getattr(Meta, 'abstract', False):
            related_name = None
            model = super_new(cls, name, bases, attrs)
            if not cls.tenant_model_class:
                cls.tenant_model_class = model
        elif getattr(Meta, 'proxy', False):
            # TODO: Handle this :D
            pass
        else:
            # Extract the specified related name if it exists.
            try:
                related_name = attrs.pop('TenantMeta').related_name
            except (KeyError, AttributeError):
                related_name = name.lower() + 's'
            Meta.abstract = True
            module = attrs.get('__module__')
            base = super_new(cls, str("Abstract%s" % name), bases, attrs)
            opts = base._meta
            model = super_new(cls, name, (base,), {
                '__module__': module,
                'Meta': meta(app_label=opts.app_label, managed=False)}
            )
            reference = Reference(related_name, model)
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
            def factory(tenant):
                object_name = str(reference.object_name_for_tenant(tenant))
                base = cls.abstract_tenant_model_factory(
                    tenant,
                    object_name,
                    bases,
                    # Add back the popped Meta and module attributes
                    dict(Meta=meta(**Meta.__dict__), __module__=module, **attrs)
                )
                tenant_Meta = meta(**Meta.__dict__)
                # TODO: Use `db_schema` once django #6148 is fixed.
                tenant_Meta.db_table = db_schema_table(tenant, model._meta.db_table)
                tenant_model = super_new(cls, object_name, (base,), {
                    'tenant': tenant,
                    '__module__': module,
                    'Meta': tenant_Meta,
                    '_tenant_meta': model._tenant_meta
                })
                ContentType.objects.get_for_model(tenant_model)
                return tenant_model
            # Attach a descriptor to the tenant model to access the underlying
            # model based on the tenant instance.
            descriptor = TenantModelDescriptor(factory, reference)
            tenant_model = get_tenant_model(model._meta.app_label)
            setattr(tenant_model, related_name, descriptor)
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

    @classmethod
    def abstract_tenant_model_factory(cls, tenant, name, bases, attrs):
        attrs['Meta'].abstract = True
        model = super(TenantModelBase, cls).__new__(cls,
            str("Abstract%s" % name),
            tuple(
                cls.references[base].model_for_tenant(tenant)
                    if isinstance(base, cls) and not base._meta.abstract
                else base for base in bases
            ),
            attrs
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
                rel.to = cls.references[to].model_for_tenant(tenant, identifier=True)
            elif to != RECURSIVE_RELATIONSHIP_CONSTANT:
                related_name = rel.related_name
                if not related_name:
                    # Hide reverse relationships with unspecified related name
                    related_name = 'unspecified_for_tenant_model+'
                rel.related_name = related_name
                clear_opts_related_cache(to)
            if isinstance(field, models.ManyToManyField):
                through = field.rel.through
                rel.through = cls.references[through].model_for_tenant(tenant, identifier=True)
                opts.local_many_to_many.remove(related_field)
            else:
                opts.local_fields.remove(related_field)
            field.contribute_to_class(model, field.name)
        return model

    def __instancecheck__(self, instance):
        return self.__subclasscheck__(instance.__class__)

    def __subclasscheck__(self, subclass):
        if isinstance(subclass, TenantModelBase):
            if (getattr(self, '_tenant_meta', None) is
                getattr(subclass, '_tenant_meta', None)):
                return True
            return any(self.__subclasscheck__(b) for b in subclass.__bases__)


class TenantModelDescriptor(object):
    def __init__(self, factory, reference):
        self.factory = factory
        self.reference = reference

    def __get__(self, tenant, owner):
        if not tenant:
            return self
        model = self.reference.model_for_tenant(tenant)
        if not model:
            model = self.factory(tenant)
        return model._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True
