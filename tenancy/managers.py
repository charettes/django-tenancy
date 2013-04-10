from __future__ import unicode_literals

from django.db import models


class AbstractTenantManager(models.Manager):
    def __init__(self):
        self.clear_cache()
        super(AbstractTenantManager, self).__init__()

    def clear_cache(self):
        self.__cache = {}

    def _get_from_cache(self, *natural_key):
        return self.__cache.get(natural_key)

    def _add_to_cache(self, tenant):
        return self.__cache.setdefault(tenant.natural_key(), tenant)

    def _remove_from_cache(self, tenant):
        return self.__cache.pop(tenant.natural_key())

    def _get_by_natural_key(self, *natural_key):
        raise NotImplementedError

    def get_by_natural_key(self, *natural_key):
        tenant = self._get_from_cache(*natural_key)
        if not tenant:
            tenant = self._add_to_cache(self._get_by_natural_key(*natural_key))
        return tenant


class TenantManager(AbstractTenantManager):
    def _get_by_natural_key(self, name):
        return self.get(name=name)
