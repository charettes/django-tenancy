from __future__ import unicode_literals
from collections import namedtuple
import copy

import django
from django.contrib.contenttypes.models import ContentType
from django.db import connections, models
from django.db.models.fields.related import RelatedField
from django.utils.datastructures import SortedDict

from . import get_tenant_model


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


class TenantOptions(object):
    def __init__(self, model_name, related_name, related_fields):
        self.model_name = model_name
        self.related_name = related_name
        self.related_fields = related_fields

    def model_name_for_tenant(self, tenant):
        return "Tenant_%s_%s" % (tenant.pk, self.model_name)

    def related_fields_for_tenant(self, tenant, opts):
        fields = {}
        for fname, related_field in self.related_fields.items():
            field = copy.deepcopy(related_field)
            to = related_field.rel.to
            if isinstance(to, basestring):
                to = TenantModelBase.references[to].model
            related_name = to._tenant_meta.related_name
            field.rel.to = getattr(tenant, related_name).model
            if isinstance(field, models.ManyToManyField):
                through = field.rel.through
                if field.rel.through:
                    if isinstance(through, basestring):
                        if '.' in through:
                            reference_key = through
                        else:
                            reference_key = "%s.%s" % (opts.app_label, through)
                        model = TenantModelBase.references[reference_key].model
                        model_name = model._tenant_meta.model_name_for_tenant(tenant)
                        field.rel.through = "%s.%s" % (model._meta.app_label, model_name)
                else:
                    if field.name is None:
                        field.name = fname
                    field.db_table = db_schema_table(tenant, field._get_m2m_db_table(opts))
            fields[fname] = field
        return fields


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


Reference = namedtuple('Reference', ['related_name', 'model'])


class TenantModelBase(models.base.ModelBase):
    # Map of instances "app_label.ObjectName" -> TenantModelSubclass
    references = SortedDict()

    def __new__(cls, name, bases, attrs):
        super_new = super(TenantModelBase, cls).__new__
        related_fields = {}
        for key, value in attrs.items():
            if isinstance(value, RelatedField):
                rel_to = value.rel.to
                if isinstance(rel_to, basestring):
                    if rel_to in cls.references:
                        related_fields[key] = attrs.pop(key)
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
            # Create the abstract model to be returned.
            model = super_new(cls, name, bases, attrs)
            opts = model._meta
            # Store instances in order to reference them with related fields
            reference_key = "%s.%s" % (opts.app_label, opts.object_name)
            cls.references[reference_key] = Reference(related_name, model)
            # Attach a descriptor to the tenant model to access the underlying
            # model based on the tenant instance.
            def new(tenant, **attrs):
                tenant_opts = model._tenant_meta
                model_name = str(tenant_opts.model_name_for_tenant(tenant))
                attrs.update(
                    tenant=tenant,
                    __module__=module,
                    **tenant_opts.related_fields_for_tenant(tenant, opts)
                )
                type_bases = [model]
                for base in bases:
                    if isinstance(base, cls):
                        base_tenant_opts = base._tenant_meta
                        base_related_name = base_tenant_opts.related_name
                        if base_related_name:
                            type_bases.append(getattr(tenant, base_related_name).model)
                            continue
                        else:
                            # Add related tenant fields of the base since it's abstract
                            attrs.update(base_tenant_opts.related_fields_for_tenant(tenant, opts))
                    elif not base._meta.abstract:
                        # model already extends this base
                        type_bases.append(base)
                return super_new(cls, model_name, tuple(type_bases), attrs)
            descriptor = TenantModelDescriptor(new, opts)
            tenant_model = get_tenant_model(model._meta.app_label)
            setattr(tenant_model, related_name, descriptor)
        else:
            related_name = None
            model = super_new(cls, name, bases, attrs)
        model._tenant_meta = TenantOptions(name, related_name, related_fields)
        return model


class TenantModelDescriptor(object):
    def __init__(self, new, opts):
        self.new = new
        self.opts = opts

    def natural_key(self, tenant):
        return (
            self.opts.app_label,
            "tenant_%s_%s" % (tenant.pk, self.opts.module_name)
        )

    def __get__(self, instance, owner):
        if not instance:
            return self
        try:
            natural_key = self.natural_key(instance)
            content_type = ContentType.objects.get_by_natural_key(*natural_key)
        except ContentType.DoesNotExist:
            # We must create the content type and the model class
            content_type = model_class = None
        else:
            # Attempt to retrieve the model class from the content type.
            # At this point, the model class can be None if it's cached yet.
            model_class = content_type.model_class()
        if model_class is None:
            # The model class has not been created yet, we define it.
            # TODO: Use `db_schema` once django #6148 is fixed.
            db_table = db_schema_table(instance, self.opts.db_table)
            model_class = self.new(
                tenant=instance,
                Meta=meta(app_label=self.opts.app_label, db_table=db_table)
            )
            # Make sure to create the content type associated with this model
            # class that was just created.
            if content_type is None:
                ContentType.objects.get_for_model(model_class)
        return model_class._default_manager


class TenantModel(models.Model):
    __metaclass__ = TenantModelBase

    class Meta:
        abstract = True
