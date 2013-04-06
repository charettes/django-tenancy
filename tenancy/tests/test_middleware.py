from __future__ import unicode_literals

from django.db import connection
from django.test.client import Client
from django.test.utils import override_settings

from .client import TenantClient
from .utils import TenancyTestCase


@override_settings(
    ROOT_URLCONF='tenancy.tests.urls',
    MIDDLEWARE_CLASSES=(
        'tenancy.middleware.GlobalTenantMiddleware',
    )
)
class GlobalTenantMiddlewareTest(TenancyTestCase):
    def setUp(self):
        super(GlobalTenantMiddlewareTest, self).setUp()
        self.client = TenantClient(self.tenant)

    def test_process_response(self):
        response = self.client.get('/global')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.tenant.name)
        self.assertRaises(AttributeError, getattr, connection, 'tenant')

    def test_process_exception(self):
        with self.assertRaisesMessage(Exception, self.tenant.name):
            self.client.get('/exception')
        self.assertRaises(AttributeError, getattr, connection, 'tenant')

    def test_non_tenant_request(self):
        """
        Ensure that the global tenant is None when none is specified.
        """
        client = Client()
        response = client.get('/global')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, '')
        self.assertRaises(AttributeError, getattr, connection, 'tenant')
