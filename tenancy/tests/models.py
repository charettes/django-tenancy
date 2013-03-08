from __future__ import unicode_literals

from django.db import models

from ..models import TenantModel
from ..monkey import patch_related_fields
from ..utils import model_sender_signals


patch_related_fields()

class AbstractTenantModel(TenantModel):
    date = models.DateField(null=True)

    class Meta:
        abstract = True


class SpecificModel(AbstractTenantModel):
    class Meta:
        app_label = 'tenancy'
        db_table = 'custom_db_table'


class SpecificModelSubclass(SpecificModel):
    class TenantMeta:
        related_name = 'specific_models_subclasses'


class RelatedSpecificModel(TenantModel):
    class TenantMeta:
        related_name = 'related_specific_models'


class AbstractSpecificModelSubclass(TenantModel):
    fk = models.ForeignKey(SpecificModel, related_name='fks', null=True)

    class Meta:
        abstract = True


class RelatedTenantModel(AbstractSpecificModelSubclass):
    fk = models.ForeignKey(SpecificModel, related_name='fks', null=True)
    m2m = models.ManyToManyField(SpecificModel, related_name='m2ms')
    m2m_through = models.ManyToManyField(SpecificModel, related_name='m2ms_through',
                                         through='M2MSpecific')

    class TenantMeta:
        related_name = 'related_tenant_models'


class M2MSpecific(TenantModel):
    related = models.ForeignKey(RelatedTenantModel)
    specific = models.ForeignKey(SpecificModel)

    class TenantMeta:
        related_name = 'm2m_specifics'


class RelatedTenantModelSubclass(RelatedTenantModel):
    pass


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