from __future__ import unicode_literals
import copy_reg

from django.db import connections, models
from django.dispatch.dispatcher import receiver
from mutant.models import (BaseDefinition, ModelDefinition,
    OrderingFieldDefinition)

from .. import get_tenant_model
from ..management import create_tenant_schema
from ..models import (db_schema_table, TenantModel, TenantModelBase,
    TenantSpecificModel)


class MutableTenantModelBase(TenantModelBase):
    @classmethod
    def tenant_model_bases(cls, tenant, bases):
        tenant_bases = super(MutableTenantModelBase, cls).tenant_model_bases(tenant, bases)
        return tuple(
            tenant_base.model_class if isinstance(base, cls) and
                not base._meta.abstract else tenant_base
            for base, tenant_base in zip(bases, tenant_bases)
        )

    def _prepare(self):
        # Skip the special `TenantModelBase._prepare` handling since all
        # `MutableTenantModelBase` instances do not need deferred preparation.
        super(TenantModelBase, self)._prepare()

    def for_tenant(self, tenant):
        if issubclass(self, TenantSpecificModel):
            raise ValueError('Can only be called on non-tenant specific model.')
        opts = self._meta
        if opts.proxy:
            return super(MutableTenantModelBase, self).for_tenant(tenant)
        reference = self.references[self]
        base = self.tenant_model_factory(tenant, abstract=True)
        # Create the model definition as managed and unmanaged it right after
        # to make sure tables are all created on tenant model creation.
        model_def, created = ModelDefinition.objects.get_or_create(
            app_label=opts.app_label,
            object_name=reference.object_name_for_tenant(tenant),
            defaults={
                'bases': (BaseDefinition(base=base),),
                'db_table': db_schema_table(tenant, opts.db_table),
                'managed': True
            }
        )
        if created:
            model_def.managed = False
            model_def.save()
            for order, lookup in enumerate(base._meta.ordering):
                if lookup.startswith('-'):
                    lookup = lookup[1:]
                    descending = True
                else:
                    descending = False
                OrderingFieldDefinition.objects.create(
                    model_def=model_def,
                    order=order,
                    lookup=lookup,
                    descending=descending
                )
        return model_def.model_class()


class MutableMutantModel(TenantModel):
    __metaclass__ = MutableTenantModelBase

    class Meta:
        abstract = True


def __unpickle_mutable_tenant_model_base(model, tenant_pk, abstract):
    tenant = get_tenant_model()._default_manager.get(pk=tenant_pk)
    if abstract:
        return model.tenant_model_factory(tenant, abstract=True)
    return model.for_tenant(tenant)


def __pickle_mutable_tenant_model_base(model):
    if issubclass(model, TenantSpecificModel):
        return (
            __unpickle_mutable_tenant_model_base,
            (model._for_tenant_model, model.tenant.pk, model._meta.abstract)
        )
    return model.__name__

copy_reg.pickle(MutableTenantModelBase, __pickle_mutable_tenant_model_base)


def get_tenant_mutable_models(tenant):
    for model in TenantModelBase.references:
        if isinstance(model, MutableTenantModelBase):
            yield model.for_tenant(tenant)


@receiver(models.signals.pre_delete, sender=get_tenant_model())
def manage_tenant_mutable_models(sender, instance, using, **kwargs):
    """
    Since the whole tenant schema is dropped on tenant deletion on PostgreSQL
    we make sure to not attempt dropping the table on model definition
    deletion. Marking the mutable model class as managed nails it since
    mutant doesn't issue DDL statement for managed models.
    """
    connection = connections[using]
    if connection.vendor == 'postgresql':
        for mutable_model in get_tenant_mutable_models(instance):
            mutable_model._meta.managed = True


models.signals.post_save.disconnect(create_tenant_schema, sender=get_tenant_model())

@receiver(models.signals.post_save, sender=get_tenant_model())
def unmanage_tenant_mutable_models(sender, instance, **kwargs):
    """
    Wrap the `create_tenant_schema` signal receiver to make sure mutable models
    are marked as managed for schema creation.
    """
    tenant_mutable_models = tuple(get_tenant_mutable_models(instance))
    for mutable_model in tenant_mutable_models:
        mutable_model._meta.managed = True
    create_tenant_schema(sender=sender, instance=instance, **kwargs)
    for mutable_model in tenant_mutable_models:
        mutable_model._meta.managed = False
