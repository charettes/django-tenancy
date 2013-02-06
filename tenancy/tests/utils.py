from __future__ import unicode_literals

from django.test.testcases import TransactionTestCase
from django.utils.unittest.case import skipIf

from ..models import Tenant
from ..settings import DEFAULT_TENANT_MODEL, TENANT_MODEL


def skipIfCustomTenant(skipped):
    return skipIf(TENANT_MODEL() != DEFAULT_TENANT_MODEL, 'Custom tenant model in use')(skipped)


@skipIfCustomTenant
class TenancyTestCase(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='tenant')
        self.other_tenant = Tenant.objects.create(name='other_tenant')

    def tearDown(self):
        Tenant.objects.all().delete()
