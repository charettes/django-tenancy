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
        self.assertIsNone(
            Tenant.objects._get_from_cache(*self.tenant.natural_key())
        )
        self.assertIsNone(
            Tenant.objects._get_from_cache(*self.other_tenant.natural_key())
        )
