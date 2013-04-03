from __future__ import unicode_literals

import django
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test.testcases import TransactionTestCase

from ..models import Tenant

from .utils import skipIfCustomTenant

# TODO: Remove when support for django 1.4 is dropped
class raise_cmd_error_stderr(object):
    def write(self, msg):
        raise CommandError(msg)


@skipIfCustomTenant
class CreateTenantCommandTest(TransactionTestCase):
    stderr = raise_cmd_error_stderr()

    def create_tenant(self, *args, **kwargs):
        if django.VERSION[:2] == (1, 4):
            kwargs['stderr'] = self.stderr
        call_command('create_tenant', *args, **kwargs)

    def test_too_many_fields(self):
        args = ('name', 'useless')
        expected_message = (
            "Number of args exceeds the number of fields for model tenancy.Tenant.\n"
            "Got %s when defined fields are ('name',)." % repr(args)
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            self.create_tenant(*args)

    def test_full_clean_failure(self):
        expected_message = (
            'Invalid value for field "name": This field cannot be blank.'
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            self.create_tenant()

    def test_success(self):
        self.create_tenant('tenant')
        Tenant.objects.get(name='tenant').delete()
