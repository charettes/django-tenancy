from __future__ import unicode_literals

import copy_reg
import logging

from django.db import connections
from django.db.models.loading import get_model
from mutant.models import (BaseDefinition, ModelDefinition,
    OrderingFieldDefinition)
from django.dispatch.dispatcher import receiver
from mutant.db.models import MutableModel
from mutant.models.model import _ModelClassProxy

from .. import get_tenant_model
from ..models import (db_schema_table, Reference, TenantModel, TenantModelBase,
    TenantSpecificModel)
from ..signals import (post_tenant_models_creation, pre_tenant_models_creation,
    pre_tenant_schema_deletion)


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


@receiver(pre_tenant_models_creation)
def manage_tenant_mutable_models(tenant, **kwargs):
    """
    Mark tenant mutable models as managed to prevent `create_tenant_schema`
    to create their associated table.
    """
    for model in tenant.models:
        if issubclass(model, MutableModel):
            model._meta.managed = True


@receiver(post_tenant_models_creation)
def unmanage_tenant_mutable_models(tenant, **kwargs):
    """
    Cleanup after our `manage_tenant_mutable_models` alteration.
    """
    for model in tenant.models:
        if issubclass(model, MutableModel):
            model._meta.managed = False


@receiver(pre_tenant_schema_deletion)
def cached_mutable_tenant_models(tenant, using, **kwargs):
    """
    Cache the mutable tenant model by bypassing their proxy.
    """
    # Since the whole tenant schema is dropped on tenant deletion on PostgreSQL
    # we make sure to not attempt dropping the table on model definition
    # deletion. Marking the mutable model class `managed` nails it since
    # mutant doesn't issue DDL statement for such models.
    managed = connections[using].vendor == 'postgresql'
    models = []
    for model in tenant.models:
        if issubclass(model, MutableModel):
            # Access the underlying model class.
            model = model.model_class
            model._meta.managed = managed
        models.append(model)
    tenant.models = tuple(models)
