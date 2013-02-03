from __future__ import unicode_literals

from django.test.testcases import TransactionTestCase
from django.utils.unittest.case import skipIf

from .. import get_tenant_model
from ..settings import DEFAULT_TENANT_MODEL, TENANT_MODEL


def skipIfCustomTenant(skipped):
    return skipIf(TENANT_MODEL != DEFAULT_TENANT_MODEL, 'Custom tenant model in use')(skipped)


class TenancyTestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tenant_model = get_tenant_model()

    def setUp(self):
        self.tenant = self.tenant_model.objects.create(name='tenant')
        self.other_tenant = self.tenant_model.objects.create(name='other_tenant')

    def tearDown(self):
        self.tenant_model.objects.all().delete()