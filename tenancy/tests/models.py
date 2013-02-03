from __future__ import unicode_literals

from django.db import models

from ..models import TenantModel


class SpecificModel(TenantModel):
    pass


class RelatedSpecificModel(TenantModel):
    class TenantMeta:
        related_name = 'related_specific_models'


class SpecificModelSubclass(SpecificModel):
    class TenantMeta:
        related_name = 'specific_models_subclasses'


class FkToTenantModel(TenantModel):
    specific_model = models.ForeignKey(SpecificModel, related_name='fks')

    class TenantMeta:
        related_name = 'fk_to_tenant_models'