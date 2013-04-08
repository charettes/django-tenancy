from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings
from django.utils.unittest.case import skipIf

from ..auth.backends import CustomTenantUserBackend
from ..settings import HAS_CUSTOM_USER_SUPPORT

from .utils import (setup_custom_tenant_user, TenancyTestCase,
    skipUnlessCustomUserSupport)


class CustomTenantUserBackendTest(TenancyTestCase):
    @skipIf(HAS_CUSTOM_USER_SUPPORT, 'Has custom user support.')
    def test_no_custom_user_support(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend requires custom user support a "
            "feature introduced in django 1.5",
            CustomTenantUserBackend
        )

    @skipUnlessCustomUserSupport
    @override_settings(AUTH_USER_MODEL='auth.User')
    def test_custom_user_not_tenant(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend can only be used with a custom "
            "tenant user model.",
            CustomTenantUserBackend
        )

    @skipUnlessCustomUserSupport
    @override_settings(AUTH_USER_MODEL='tenancy.TenantUser')
    def test_missing_connection_tenant(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend requires that a `tenant` attribute "
            "be set on the default connection to work properly. The "
            "`tenancy.middleware.GlobalTenantMiddlewareTest` does "
            "just that.",
            CustomTenantUserBackend
        )

    @setup_custom_tenant_user
    def test_authenticate(self):
        with self.tenant.as_global():
            backend = CustomTenantUserBackend()
        user = self.tenant.users.model(email='p.roy@habs.ca')
        user.set_password('numero 33')
        user.save()
        self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca'))
        self.assertIsNone(backend.authenticate('p.roy@habs.ca'))
        self.assertTrue(backend.authenticate('p.roy@habs.ca', 'numero 33'))

    @setup_custom_tenant_user
    def test_get_user(self):
        with self.tenant.as_global():
            backend = CustomTenantUserBackend()
        user = self.tenant.users.create(email='latitude-e4200@dell.com')
        self.assertIsNone(backend.get_user(user.pk+1))
        self.assertEqual(user, backend.get_user(user.pk))
