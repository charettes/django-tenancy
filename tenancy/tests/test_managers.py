from __future__ import unicode_literals

from ..models import Tenant

from .utils import TenancyTestCase


class TenantManagerTest(TenancyTestCase):
    def test_cache_on_init(self):
        # They were cached on `setUp`.
        self.assertEqual(
            id(self.tenant),
            id(Tenant.objects.get_by_natural_key(
                *self.tenant.natural_key()
            ))
        )
        self.assertEqual(
            id(self.other_tenant),
            id(Tenant.objects.get_by_natural_key(
                *self.other_tenant.natural_key()
            ))
        )
        Tenant.objects.clear_cache()
        for tenant in Tenant.objects.all():
            self.assertEqual(
                id(tenant),
                id(Tenant.objects._get_from_cache(*tenant.natural_key()))
            )

    def test_clear_cache(self):
        # They were cached on `setUp`.
        Tenant.objects.clear_cache()
        with self.assertRaises(KeyError):
            Tenant.objects._get_from_cache(*self.tenant.natural_key())
        with self.assertRaises(KeyError):
            Tenant.objects._get_from_cache(*self.other_tenant.natural_key())


class TenantModelsCacheTest(TenancyTestCase):
    def test_initialized_models(self):
        """
        Make sure models are loaded upon model initialization.
        """
        self.assertIn('models', self.tenant.__dict__)
