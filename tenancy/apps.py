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

        # Remove when dropping support for Django 1.7
        from django.db.models.options import Options
        verbose_name_raw = Options.verbose_name_raw.fget
        if hasattr(verbose_name_raw, '_patched'):
            return

        def _get_verbose_name_raw(self):
            name = verbose_name_raw(self)
            if len(name) >= 40:
                name = "%s..." % name[0:36]
            return name
        _get_verbose_name_raw.patched = True
        Options.verbose_name_raw = property(_get_verbose_name_raw)
