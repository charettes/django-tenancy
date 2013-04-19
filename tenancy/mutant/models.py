from __future__ import unicode_literals
import copy_reg
import logging

from django.db import connections, models
from django.db.models.loading import get_model
from mutant.models import (BaseDefinition, ModelDefinition,
    OrderingFieldDefinition)
from mutant.db.models import MutableModel
from mutant.models.model import _ModelClassProxy

from .. import get_tenant_model
from ..management import create_tenant_schema, tenant_model_receiver
from ..models import (db_schema_table, Reference, TenantModel, TenantModelBase,
    TenantSpecificModel)


class MutableReference(Reference):
    def for_tenant(self, tenant):
        return self.model.for_tenant(tenant)


class MutableTenantModelBase(TenantModelBase):
    reference = MutableReference

    @classmethod
    def tenant_model_bases(cls, tenant, bases):
        tenant_bases = super(MutableTenantModelBase, cls).tenant_model_bases(tenant, bases)
        return tuple(
            tenant_base.model_class if isinstance(base, cls) and
                not base._meta.abstract else tenant_base
            for base, tenant_base in zip(bases, tenant_bases)
        )

    def for_tenant(self, tenant):
        if issubclass(self, TenantSpecificModel):
            raise ValueError('Can only be called on non-tenant specific model.')
        opts = self._meta
        if opts.proxy:
            return super(MutableTenantModelBase, self).for_tenant(tenant)

        reference = self.references[self]
        app_label = opts.app_label
        object_name = reference.object_name_for_tenant(tenant)

        # Return the already cached model instead of creating a new one.
        model = get_model(
            opts.app_label, object_name.lower(),
            only_installed=False
        )
        if model:
            return _ModelClassProxy(model)

        base = self.abstract_tenant_model_factory(tenant)
        # Create the model definition as managed and unmanaged it right after
        # to make sure tables are all created on tenant model creation.
        model_def, created = ModelDefinition.objects.get_or_create(
            app_label=app_label,
            object_name=object_name,
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


class MutableTenantModel(TenantModel):
    __metaclass__ = MutableTenantModelBase

    class Meta:
        abstract = True


def __unpickle_mutable_tenant_model_base(model, natural_key, abstract):
    try:
        manager = get_tenant_model()._default_manager
        tenant = manager.get_by_natural_key(*natural_key)
        if abstract:
            return model.abstract_tenant_model_factory(tenant)
        return model.for_tenant(tenant)
    except Exception:
        logger = logging.getLogger('tenancy.pickling')
        logger.exception('Failed to unpickle mutable tenant model')


def __pickle_mutable_tenant_model_base(model):
    if issubclass(model, TenantSpecificModel):
        return (
            __unpickle_mutable_tenant_model_base,
            (model._for_tenant_model, model.tenant.natural_key(), model._meta.abstract)
        )
    return model.__name__

copy_reg.pickle(MutableTenantModelBase, __pickle_mutable_tenant_model_base)


def manage_tenant_mutable_models(tenant, managed=True):
    """
    Mark tenant specific mutable models as managed.
    """
    for model in tenant.models:
        if issubclass(model, MutableModel):
            model._meta.managed = managed


tenant_model_receiver.disconnect(models.signals.post_save, create_tenant_schema)


@tenant_model_receiver(models.signals.post_save)
def create_mutant_tenant_schema(sender, instance, **kwargs):
    """
    Wrap the `create_tenant_schema` signal receiver to make sure mutable models
    are marked as managed for schema creation. We can't use `pre_save` since
    the tenant doesn't exist yet.
    """
    instance._default_manager._add_to_cache(instance)
    manage_tenant_mutable_models(instance)
    create_tenant_schema(sender=sender, instance=instance, **kwargs)
    manage_tenant_mutable_models(instance, False)


@tenant_model_receiver(models.signals.pre_delete)
def cache_mutable_tenant_models(sender, instance, using, **kwargs):
    """
    Cache the mutable tenant model by bypassing their proxy.
    """
    # Since the whole tenant schema is dropped on tenant deletion on PostgreSQL
    # we make sure to not attempt dropping the table on model definition
    # deletion. Marking the mutable model class as managed nails it since
    # mutant doesn't issue DDL statement for managed models.
    managed = connections[using].vendor == 'postgresql'
    models = []
    for model in instance.models:
        if issubclass(model, MutableModel):
            model = model.model_class
            model._meta.managed = managed
        models.append(model)
    instance.models = tuple(models)
