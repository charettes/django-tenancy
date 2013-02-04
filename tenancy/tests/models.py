from __future__ import unicode_literals

from django.db import models

from ..management import model_sender_signals
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