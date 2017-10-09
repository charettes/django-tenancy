from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.test.client import RequestFactory
from django.test.utils import override_settings

from tenancy.auth.backends import TenantUserBackend

from .utils import TenancyTestCase


class TenantUserBackendTests(TenancyTestCase):
    @override_settings(AUTH_USER_MODEL='auth.User')
    def test_custom_user_not_tenant(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "The `tenancy.auth.backends.TenantUserBackend` "
            "authentification backend can only be used with a custom "
            "tenant user model.",
            TenantUserBackend
        )

    @override_settings(AUTH_USER_MODEL='tests.TenantUser')
    def test_authenticate(self):
        user = self.tenant.users.model(email='p.roy@habs.ca')
        user.set_password('numero 33')
        user.save()
        backend = TenantUserBackend()
        # Test globally.
        with self.tenant.as_global():
            self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca'))
            self.assertIsNone(backend.authenticate(email='p.roy@habs.ca'))
            self.assertEqual(backend.authenticate(email='p.roy@habs.ca', password='numero 33'), user)
        # Test request.
        request = RequestFactory().get('/')
        setattr(request, backend.tenant_model.ATTR_NAME, self.tenant)
        self.assertIsNone(backend.authenticate(request=request, username='nobody@nowhere.ca'))
        self.assertIsNone(backend.authenticate(request=request, email='p.roy@habs.ca'))
        self.assertEqual(backend.authenticate(request=request, email='p.roy@habs.ca', password='numero 33'), user)
        # Test explicit.
        self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca', tenant=self.tenant))
        self.assertIsNone(backend.authenticate(username='p.roy@habs.ca', tenant=self.tenant))
        self.assertEqual(
            backend.authenticate(username='p.roy@habs.ca', password='numero 33', tenant=self.tenant), user
        )
        # Test explicit using ATTR_NAME.
        type(self.tenant).ATTR_NAME = 'foo'
        try:
            self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca', foo=self.tenant))
            self.assertIsNone(backend.authenticate(username='p.roy@habs.ca', foo=self.tenant))
            self.assertEqual(
                backend.authenticate(username='p.roy@habs.ca', password='numero 33', foo=self.tenant), user
            )
        finally:
            del type(self.tenant).ATTR_NAME
        # Test missing.
        self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca'))
        self.assertIsNone(backend.authenticate(username='p.roy@habs.ca'))
        self.assertIsNone(backend.authenticate(username='p.roy@habs.ca', password='numero 33'))

    @override_settings(AUTH_USER_MODEL='tests.TenantUser')
    def test_get_user(self):
        backend = TenantUserBackend()
        user = self.tenant.users.create(email='latitude-e4200@dell.com')
        with self.tenant.as_global():
            self.assertIsNone(backend.get_user(user.pk + 1))
            self.assertEqual(user, backend.get_user(user.pk))
