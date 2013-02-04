from __future__ import unicode_literals

from django.db import models

from ..management import model_sender_signals
from ..models import TenantModel
from ..monkey import patch_related_fields


patch_related_fields()

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


class AbstractSpecificModelSubclass(TenantModel):
    fk = models.ForeignKey(SpecificModel, related_name='fks', null=True)

    class Meta:
        abstract = True


class RelatedTenantModel(AbstractSpecificModelSubclass):
    fk = models.ForeignKey(SpecificModel, related_name='fks', null=True)
    m2m = models.ManyToManyField(SpecificModel, related_name='m2ms')

    class TenantMeta:
        related_name = 'related_tenant_models'


class SignalTenantModel(TenantModel):
    class TenantMeta:
        related_name = 'signal_models'

    _logs = {}

    @classmethod
    def logs(cls):
        return cls._logs.setdefault(cls.tenant, [])

    @classmethod
    def log(cls, signal):
        cls.logs().append(signal)

def add_to_dispatched(signal, sender, **kwargs):
    sender.log(signal)

for signal in model_sender_signals:
    signal.connect(add_to_dispatched, sender=SignalTenantModel)