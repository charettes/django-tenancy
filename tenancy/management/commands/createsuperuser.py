from __future__ import unicode_literals
from optparse import make_option

from django.contrib.auth.management.commands.createsuperuser import Command
from django.core.management.base import CommandError

from ... import get_tenant_model


def get_tenant_by_natural_key(option, opt, value, parser):
    natural_key = value.split(',')
    tenant_model = get_tenant_model()
    tenant = tenant_model._default_manager.get_by_natural_key(*natural_key)
    parser.values.tenant = tenant


class Command(Command):
    def __init__(self):
        super(Command, self).__init__()
        from ...settings import TENANT_AUTH_USER_MODEL
        self.tenant_auth_user_model = TENANT_AUTH_USER_MODEL
        if self.tenant_auth_user_model:
            self.option_list += (
                make_option(
                    '--tenant', action='callback', dest='tenant', type='str',
                    callback=get_tenant_by_natural_key,
                    help='Specifies the tenant to use by comma separated natural key.'
                ),
            )

    def handle(self, *args, **kwargs):
        tenant = kwargs.get('tenant')
        if tenant:
            self.UserModel = self.UserModel.for_tenant(tenant)
        elif self.tenant_auth_user_model:
            raise CommandError(
                "Since your swapped `AUTH_USER_MODEL` is tenant specific "
                "you must specify a tenant."
            )
        return super(Command, self).handle(*args, **kwargs)
