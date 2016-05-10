from __future__ import unicode_literals

from django.apps import AppConfig
from django.db.models import signals

from . import get_tenant_model


class TenancyConfig(AppConfig):
    name = 'tenancy'

    def clear_tenant_model_cache(self, **kwargs):
        get_tenant_model()._default_manager.clear_cache()

    def ready(self):
        # Prevents migrate from taking tenant models into consideration when
        # detecting changes.
        signals.pre_migrate.connect(self.clear_tenant_model_cache)
