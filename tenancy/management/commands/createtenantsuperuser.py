from __future__ import unicode_literals

from optparse import make_option

from django.contrib.auth.management.commands.createsuperuser import Command
from django.core.management.base import CommandError

from ... import get_tenant_model
from ...models import TenantModelBase


def get_tenant_by_natural_key(option, opt, value, parser):
    natural_key = value.split(',')
    tenant_model = get_tenant_model()
    tenant = tenant_model._default_manager.get_by_natural_key(*natural_key)
    parser.values.tenant = tenant


class Command(Command):
    requires_system_checks = False
    option_list = Command.option_list + (
        make_option(
            '--tenant', action='callback', dest='tenant', type='str',
            callback=get_tenant_by_natural_key,
            help='Specifies the tenant to use by comma separated natural key.'
        ),
    )

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        if not isinstance(self.UserModel, TenantModelBase):
            raise CommandError(
                "The defined user model (%s) is not tenant specific." % self.UserModel._meta
            )

    def handle(self, *args, **kwargs):
        tenant = kwargs.get('tenant')
        self.UserModel = self.UserModel.for_tenant(tenant)
        return super(Command, self).handle(*args, **kwargs)
