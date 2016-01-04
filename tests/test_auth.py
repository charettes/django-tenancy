from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings

from tenancy.auth.backends import CustomTenantUserBackend

from .utils import TenancyTestCase


class CustomTenantUserBackendTest(TenancyTestCase):
    @override_settings(AUTH_USER_MODEL='auth.User')
    def test_custom_user_not_tenant(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend can only be used with a custom "
            "tenant user model.",
            CustomTenantUserBackend
        )

    @override_settings(AUTH_USER_MODEL='tests.TenantUser')
    def test_missing_connection_tenant(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend requires that a `tenant` attribute "
            "be set on the default connection to work properly. The "
            "`tenancy.middleware.GlobalTenantMiddleware` does "
            "just that.",
            CustomTenantUserBackend
        )

    @override_settings(AUTH_USER_MODEL='tests.TenantUser')
    def test_authenticate(self):
        with self.tenant.as_global():
            backend = CustomTenantUserBackend()
        user = self.tenant.users.model(email='p.roy@habs.ca')
        user.set_password('numero 33')
        user.save()
        self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca'))
        self.assertIsNone(backend.authenticate('p.roy@habs.ca'))
        self.assertTrue(backend.authenticate('p.roy@habs.ca', 'numero 33'))

    @override_settings(AUTH_USER_MODEL='tests.TenantUser')
    def test_get_user(self):
        with self.tenant.as_global():
            backend = CustomTenantUserBackend()
        user = self.tenant.users.create(email='latitude-e4200@dell.com')
        self.assertIsNone(backend.get_user(user.pk + 1))
        self.assertEqual(user, backend.get_user(user.pk))
