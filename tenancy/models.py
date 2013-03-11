from __future__ import unicode_literals
from collections import namedtuple
import copy

import django
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, models
from django.db.models.base import ModelBase
from django.db.models.fields.related import (RelatedField,
    RECURSIVE_RELATIONSHIP_CONSTANT)
from django.db.models.loading import get_model
from django.utils.datastructures import SortedDict

from . import get_tenant_model
from .utils import clear_opts_related_cache, model_name_from_opts


class AbstractTenant(models.Model):
    class Meta:
        abstract = True

    @property
    def db_schema(self):
        raise NotImplementedError


class Tenant(AbstractTenant):
    name = models.CharField(unique=True, max_length=20)

    class Meta:
        if django.VERSION >= (1, 5):
            swappable = 'TENANCY_TENANT_MODEL'

    @property
    def db_schema(self):
        return "tenant_%s" % self.name


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
    if connection.vendor == 'postgresql':
        # See https://code.djangoproject.com/ticket/6148#comment:47
        return '%s\".\"%s' % (tenant.db_schema, db_table)
    else:
        return "%s_%s" % (tenant.db_schema, db_table)


class Reference(object):
    __slots__ = ('identifier', 'related_name', 'model')

    def __init__(self, identifier, related_name, model):
        self.identifier = identifier
        self.related_name = related_name
        self.model = model

    def object_name_for_tenant(self, tenant):
        return "Tenant_%s_%s" % (tenant.pk, self.model._meta.object_name)

    def model_for_tenant(self, tenant, identifier=False):
        app_label = self.model._meta.app_label
        object_name = self.object_name_for_tenant(tenant)
        model = get_model(app_label, object_name.lower(), only_installed=False)
        if model:
            return model
        elif identifier:
            return "%s.%s" % (app_label, object_name)


class TenantModelBase(ModelBase):
    references = SortedDict() # Map of instances "app_label.ObjectName" -> TenantModelBaseInstance
    base = None # Reference to the first declared instance of TenantModelBase

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        for attr, value in attrs.items():
            if isinstance(value, RelatedField):
                cls.validate_related_name(name, attr, value)
        Meta = attrs.setdefault('Meta', meta())
        # It's not an abstract model
        if not getattr(Meta, 'abstract', False):
            Meta.abstract = True
            module = attrs.get('__module__')
            # Extract the specified related name if it exists.
            try:
                related_name = attrs.pop('TenantMeta').related_name
            except (KeyError, AttributeError):
                related_name = name.lower() + 's'
            # Make sure the tenant model base is not subclassing other tenant
            # model bases.
            model_bases = tuple(
                base for base in bases
                if not isinstance(base, cls) or
                   not base._tenant_meta.related_name
            ) or (cls.base,)
            model = super_new(cls, name, model_bases, attrs)
            opts = model._meta
            # Store instances in order to reference them with related fields
            identifier = "%s.%s" % (opts.app_label, opts.object_name)
            reference = Reference(identifier, related_name, model)
            cls.references[identifier] = reference
            # Create missing intermediary model
            for m2m in opts.local_many_to_many:
                if not m2m.rel.through:
                    m2m.rel.through = cls.intermediary_model_factory(m2m, reference)
            def new(tenant):
                attrs = {
                    'tenant': tenant,
                    '__module__': module,
                    'Meta': meta(
                        app_label=opts.app_label,
                        # TODO: Use `db_schema` once django #6148 is fixed.
                        db_table=db_schema_table(tenant, opts.db_table),
                    ),
                    '_tenant_meta': TenantOptions(name, related_name, model)
                }
                if opts.auto_created:
                    from_related_name = opts.auto_created._tenant_meta.related_name
                    auto_created_for = getattr(tenant, from_related_name).model
                    attrs['Meta'].auto_created = auto_created_for
                new_bases = [cls.base_for_tenant(model, tenant, reference)]
                for base in bases:
                    if isinstance(base, cls):
                        base_tenant_opts = base._tenant_meta
                        base_related_name = base_tenant_opts.related_name
                        if base_related_name:
                            tenant_base = getattr(tenant, base_related_name).model
                            new_bases.append(tenant_base)
                        else: assert issubclass(model, base)  # Safeguard
                    elif not isinstance(base, ModelBase) or not base._meta.abstract:
                        new_bases.append(base)
                object_name = str(reference.object_name_for_tenant(tenant))
                tenant_model = super_new(cls, object_name, tuple(new_bases), attrs)
                ContentType.objects.get_for_model(tenant_model)
                return tenant_model
            # Attach a descriptor to the tenant model to access the underlying
            # model based on the tenant instance.
            descriptor = TenantModelDescriptor(new, reference)
            tenant_model = get_tenant_model(model._meta.app_label)
            setattr(tenant_model, related_name, descriptor)
        else:
            related_name = None
            model = super_new(cls, name, bases, attrs)
            if not cls.base:
                cls.base = model
        model._tenant_meta = TenantOptions(name, related_name, None)
        return model

    @classmethod
    def validate_related_name(cls, name, attr, field):
        """
        Make sure that related fields pointing to non-tenant models specify
        a related name containing a %(tenant)s format placeholder.
        """
        to = field.rel.to
        if isinstance(to, basestring):
            # TODO: Post-pone validation
            pass
        elif not isinstance(to, cls):
            related_name = field.rel.related_name
            if (related_name is not None and
                not (field.rel.is_hidden() or '%(tenant)s' in related_name)):
                    raise ImproperlyConfigured(
                        "Since `%s.%s` is originating for an instance "
                        "of `TenantModelBase` and not pointing to one "
                        "it's `related_name` option must ends with a "
                        "'+' or contain the '%%(tenant)s' format "
                        "placeholder." % (name, attr)
                    )


    @classmethod
    def intermediary_model_factory(cls, field, reference):
        from_model = reference.model
        to_model = field.rel.to
        opts = from_model._meta
        from_model_name = model_name_from_opts(opts)
        managed = True
        if to_model == RECURSIVE_RELATIONSHIP_CONSTANT:
            from_ = "from_%s" % from_model_name
            to = "to_%s" % from_model_name
            to_model = from_model
            managed = opts.managed
        else:
            from_ = from_model_name
            if isinstance(to_model, basestring):
                to = to_model.split('.')[-1].lower()
                # TODO: Handle managed in this case
            else:
                to = model_name_from_opts(to_model._meta)
                managed = opts.managed or to_model._meta.managed
        name = '%s_%s' % (opts.object_name, field.name)
        Meta = meta(
            db_table=field._get_m2m_db_table(opts),
            managed=managed,
            auto_created=reference.model,
            app_label=opts.app_label,
            db_tablespace=opts.db_tablespace,
            unique_together=(from_, to),
            verbose_name="%(from)s-%(to)s relationship" % {'from': from_, 'to': to},
            verbose_name_plural="%(from)s-%(to)s relationships" % {'from': from_, 'to': to}
        )
        # TODO: Add support for db_constraints
        return cls(str(name), (TenantModel,), {
            'Meta': Meta,
            '__module__': reference.model.__module__,
            from_: models.ForeignKey(
                reference.identifier, related_name="%s+" % name,
                db_tablespace=field.db_tablespace
            ),
            to: models.ForeignKey(
                to_model, related_name="%s+" % name,
                db_tablespace=field.db_tablespace
            ),
        })

    @classmethod
    def base_for_tenant(cls, model, tenant, reference):
        """
        Creates an abstract base with replaced related fields to be used when
        creating concrete tenant models.
        """
        object_name = str("Abstract%s" % reference.object_name_for_tenant(tenant))
        attrs = {
            'Meta': meta(abstract=True),
            '__module__': model.__module__
        }
        base = cls(object_name, (model,), attrs)
        opts = base._meta
        local_related_fields = [
            field for field in opts.local_fields
            if isinstance(field, RelatedField)
        ] + opts.local_many_to_many
        for related_field in local_related_fields:
            field = copy.deepcopy(related_field)
            to = field.rel.to
            if isinstance(to, basestring):
                if '.' not in to:
                    to = "%s.%s" % (opts.app_label, to)
                to_reference = cls.references.get(to)
                if to_reference:
                    # This field points to a tenant model, we must replace it.
                    field = copy.deepcopy(related_field)
                    field.rel.to = to_reference.model_for_tenant(tenant, identifier=True)
            elif not isinstance(to, cls):
                related_name = field.rel.related_name
                if related_name is None:
                    # Hide reverse relationships with unspecified related name
                    related_name = 'unspecified_for_tenant_model+'
                else:
                    related_name = related_name % {
                        'app_label': model._meta.app_label,
                        'class': model_name_from_opts(model._meta),
                        'tenant': tenant.db_schema
                    }
                field.rel.related_name = related_name
                clear_opts_related_cache(to)
            if isinstance(field, models.ManyToManyField):
                through = field.rel.through
                if isinstance(through, cls):
                    through = "%s.%s" % (
                        through._meta.app_label,
                        through._meta.object_name
                    )
                elif '.' not in through:
                    through = "%s.%s" % (opts.app_label, through)
                through_reference = cls.references[through]
                field.rel.through = through_reference.model_for_tenant(
                    tenant, identifier=True
                )
                opts.local_many_to_many.remove(related_field)
            else:
                opts.local_fields.remove(related_field)
            field.contribute_to_class(base, field.name)
        return base


class TenantModelDescriptor(object):
    def __init__(self, new, reference):
        self.new = new
        self.reference = reference

    def __get__(self, tenant, owner):
        if not tenant:
            return self
        model = self.reference.model_for_tenant(tenant)
        if not model:
            model = self.new(tenant)
        return model._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True
