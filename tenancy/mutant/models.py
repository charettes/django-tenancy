from __future__ import unicode_literals

import logging

from django.utils import six
from django.utils.six.moves import copyreg
from django.dispatch.dispatcher import receiver
from mutant.db.models import MutableModel
from mutant.models import (
    BaseDefinition, ModelDefinition, OrderingFieldDefinition
)
try:
    from mutant.models.model import MutableModelProxy
except ImportError:
    from mutant.models.model import _ModelClassProxy as MutableModelProxy
from mutant.signals import mutable_class_prepared

from .. import get_tenant_model
from ..models import (
    db_schema_table, Reference, TenantModel, TenantModelBase,
    TenantSpecificModel
)
from ..signals import (
    post_models_creation, pre_models_creation, pre_schema_deletion
)
from ..utils import get_model


class MutableReference(Reference):
    def for_tenant(self, tenant):
        return self.model.for_tenant(tenant)


class MutableTenantModelBase(TenantModelBase):
    reference = MutableReference

    @classmethod
    def tenant_model_bases(cls, tenant, bases):
        tenant_bases = super(MutableTenantModelBase, cls).tenant_model_bases(tenant, bases)
        return tuple(
            tenant_base.__get__(None, None)
            if isinstance(base, cls) and not base._meta.abstract else tenant_base
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
            opts.app_label, object_name.lower(), only_installed=False
        )
        if model:
            return MutableModelProxy(model)

        base = self.abstract_tenant_model_factory(tenant)
        # Create the model definition as managed and unmanage it right after
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
            model_def.save(update_fields=['managed'])
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


class MutableTenantModel(six.with_metaclass(MutableTenantModelBase, TenantModel)):
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
        tenant = getattr(model, get_tenant_model().ATTR_NAME)
        return (
            __unpickle_mutable_tenant_model_base,
            (model._for_tenant_model, tenant.natural_key(), model._meta.abstract)
        )
    return model.__name__

copyreg.pickle(MutableTenantModelBase, __pickle_mutable_tenant_model_base)


@receiver(mutable_class_prepared)
def contribute_to_related_mutable_class(sender, existing_model_class, **kwargs):
    """
    Since related fields are contributing to the related class only once (on
    the first time `class_prepared` is triggered) we make sure they also do
    the same with mutated classes they relate to in order to attach objects
    such as reverse descriptor.
    """
    if existing_model_class:
        related_objects = (
            related_object for related_object, model in
            sender._meta.get_all_related_objects_with_model() if model is None
        )
        for related_object in related_objects:
            field = related_object.field
            field.contribute_to_related_class(sender, field.related)


@receiver(pre_models_creation)
def manage_mutable_models(tenant, **kwargs):
    """
    Mark tenant mutable models as managed to prevent `create_tenant_schema`
    to create their associated table.
    """
    for model in tenant.models:
        if issubclass(model, MutableModel):
            model._meta.managed = True


@receiver(post_models_creation)
def unmanage_mutable_models(tenant, **kwargs):
    """
    Cleanup after our `manage_mutable_models` alteration.
    """
    for model in tenant.models:
        if issubclass(model, MutableModel):
            model._meta.managed = False


@receiver(pre_schema_deletion)
def cached_mutable_models(tenant, using, **kwargs):
    """
    Cache the mutable tenant model by bypassing their proxy and mark them as
    managed to prevent `drop_tenant_schema` from dropping their associated
    table twice.
    """
    models = []
    for model in tenant.models:
        if issubclass(model, MutableModel):
            # Access the underlying model class.
            model = model.__get__(None, None)
            opts = model._meta
            opts.managed = True
            # Repoint all local related object to the existing model class to
            # prevent access to the definition once it's deleted.
            for related_object in opts.get_all_related_objects(local_only=True):
                related_object.field.rel.to = model
        models.append(model)
    tenant.models = tuple(models)
