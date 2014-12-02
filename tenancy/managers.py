from __future__ import unicode_literals

from django.db import models


class AbstractTenantManager(models.Manager):
    def __init__(self):
        self.__cache = {}
        super(AbstractTenantManager, self).__init__()

    def clear_cache(self):
        for tenant in list(self.__cache.values()):
            self._remove_from_cache(tenant)

    def _get_from_cache(self, *natural_key):
        return self.__cache[natural_key]

    def _add_to_cache(self, tenant):
        key = tenant.natural_key()
        try:
            return self._get_from_cache(*key)
        except KeyError:
            self.__cache[key] = tenant
        return tenant

    def _remove_from_cache(self, tenant):
        key = tenant.natural_key()
        delattr(tenant, 'models')
        return self.__cache.pop(key)

    def _get_by_natural_key(self, *natural_key):
        raise NotImplementedError

    def get_by_natural_key(self, *natural_key):
        try:
            tenant = self._get_from_cache(*natural_key)
        except KeyError:
            tenant = self._add_to_cache(self._get_by_natural_key(*natural_key))
        return tenant


class TenantManager(AbstractTenantManager):
    def _get_by_natural_key(self, name):
        return self.get(name=name)


class TenantModelManagerDescriptor(object):
    """
    This class provides a better error message when you try to access a
    manager on an tenant model.
    """
    def __init__(self, model):
        self.model = model

    def __get__(self, instance, owner):
        raise AttributeError(
            "Manager isn't available; %s is tenant specific" % (
                self.model._meta.object_name,
            )
        )
