from __future__ import unicode_literals
import logging

from django.dispatch.dispatcher import receiver
from django.test.signals import setting_changed
from django.test.testcases import TransactionTestCase
from django.utils.unittest.case import skipIf

from .. import settings
from ..models import Tenant


logger = logging.getLogger('tenancy.tests')

def skipIfCustomTenant(skipped):
    return skipIf(
        settings.TENANT_MODEL != settings.DEFAULT_TENANT_MODEL,
        'Custom tenant model in use'
    )(skipped)


@skipIfCustomTenant
class TenancyTestCase(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='tenant')
        self.other_tenant = Tenant.objects.create(name='other_tenant')

    def tearDown(self):
        Tenant.objects.all().delete()


@receiver(setting_changed)
def reload_settings_module(signal, sender, setting, value):
    if setting in ('AUTH_USER_MODEL', 'TENANCY_TENANT_MODEL'):
        logger.debug(
            "Attempt reload of settings because `%s` has changed to %r." % (setting, value)
        )
        try:
            reload(settings)
        except Exception:
            logger.exception("Failed to reload the settings module.")
        else:
            logger.debug("Successfully reloaded the settings module.")
