from __future__ import unicode_literals

from django.db import models

from ..models import TenantModel


class AbstractTenantModel(TenantModel):
    class Meta:
        abstract = True


class SpecificModel(AbstractTenantModel):
    class Meta:
        db_table = 'custom_db_table'


class RelatedSpecificModel(TenantModel):
    class TenantMeta:
        related_name = 'related_specific_models'


class SpecificModelSubclass(SpecificModel):
    class TenantMeta:
        related_name = 'specific_models_subclasses'


class FkToTenantModel(TenantModel):
    specific_model = models.ForeignKey('tests.SpecificModel', related_name='fks')

    class TenantMeta:
        related_name = 'fk_to_tenant_models'