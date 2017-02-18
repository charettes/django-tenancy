from __future__ import unicode_literals

import threading

from django.db import models

try:
    from django.db.models.query import ModelIterable
except ImportError:
    # TODO: Remove when dropping support for Django 1.8.
    class TenantQueryset(models.QuerySet):
        def iterator(self):
            iterator = super(TenantQueryset, self).iterator()
            add_to_cache = self.model._default_manager._add_to_cache
            for tenant in iterator:
                yield add_to_cache(tenant)
else:
    class TenantIterable(ModelIterable):
        def __iter__(self):
            iterator = super(TenantIterable, self).__iter__()
            add_to_cache = self.queryset.model._default_manager._add_to_cache
            for tenant in iterator:
                yield add_to_cache(tenant)

    class TenantQueryset(models.QuerySet):
        def __init__(self, *args, **kwargs):
            super(TenantQueryset, self).__init__(*args, **kwargs)
            self._iterable_class = TenantIterable


class AbstractTenantManager(models.Manager.from_queryset(TenantQueryset)):
    __cache = threading.local()

    @property
    def _tenants(self):
        try:
            return self.__cache.tenants
        except AttributeError:
            tenants = {}
            setattr(self.__cache, 'tenants', tenants)
            return tenants

    def clear_cache(self):
        for tenant in list(self._tenants.values()):
            self._remove_from_cache(tenant)

    def should_cache(self, tenant):
        """Return whether or not a tenant instance should be cached."""
        # TODO: Remove when dropping support for Django 1.9 and simply return True.
        return not getattr(tenant, '_deferred', False)

    def _get_from_cache(self, *natural_key):
        return self._tenants[natural_key]

    def _add_to_cache(self, tenant):
        if self.should_cache(tenant):
            key = tenant.natural_key()
            try:
                return self._get_from_cache(*key)
            except KeyError:
                self._tenants[key] = tenant
        return tenant

    def _remove_from_cache(self, tenant):
        key = tenant.natural_key()
        delattr(tenant, 'models')
        tenant.__class__.models.tenant_models.pop(key, None)
        return self._tenants.pop(key)

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
