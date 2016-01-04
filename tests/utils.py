from __future__ import unicode_literals

import logging
from collections import OrderedDict
from functools import wraps
from imp import reload

from django.contrib.auth.management.commands import createsuperuser
from django.dispatch.dispatcher import receiver
from django.test.signals import setting_changed
from django.test.testcases import TransactionTestCase
from django.utils.six.moves import input

from tenancy import settings
from tenancy.management.commands import createtenant
from tenancy.models import Tenant

logger = logging.getLogger('tests')


class TenancyTestCase(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='tenant')
        self.other_tenant = Tenant.objects.create(name='other_tenant')

    def tearDown(self):
        for tenant in Tenant.objects.all():
            tenant.delete()

        # Remove references to tenants to allow them and their associated
        # models to be garbage collected since unittest2 suites might keep
        # references to testcases.
        # See http://bugs.python.org/issue11798 for more details.
        del self.tenant
        del self.other_tenant


@receiver(setting_changed)
def reload_settings_module(signal, sender, setting, value, **kwargs):
    if setting.startswith('TENANCY_'):
        logger.debug(
            "Attempt reload of settings because `%s` has changed to %r." % (
                setting, value
            )
        )
        try:
            reload(settings)
        except Exception:
            logger.exception("Failed to reload the settings module.")
        else:
            logger.debug("Successfully reloaded the settings module.")


class Replier(object):
    def __init__(self, replies):
        self.replies = OrderedDict(replies)

    def __call__(self, prompt):
        for p in self.replies:
            if prompt.startswith(p):
                return self.replies[p]
        else:
            raise ValueError("No reply defined for %s" % prompt)


class GetPass(Replier):
    def __init__(self, replier):
        self.replier = replier

    def getpass(self, prompt='Password'):
        return self.replier.__call__(prompt)


def mock_inputs(inputs):
    """
    Decorator to temporarily replace input/getpass to allow interactive
    createsuperuser.
    """
    def inner(test_func):
        @wraps(test_func)
        def wrapped(*args):
            replier = Replier(inputs)
            getpass = createsuperuser.getpass
            createsuperuser.input = replier
            createsuperuser.getpass = GetPass(replier)
            createtenant.input = replier
            try:
                test_func(*args)
            finally:
                createsuperuser.input = input
                createtenant.input = input
                createsuperuser.getpass = getpass
        return wrapped
    return inner
