from __future__ import unicode_literals

import argparse

import django
from django.contrib.auth.management.commands.createsuperuser import Command
from django.core.management.base import CommandError

from ... import get_tenant_model
from ...models import TenantModelBase


def get_tenant_by_natural_key(option, opt, value, parser):
    natural_key = value.split(',')
    tenant_model = get_tenant_model()
    tenant = tenant_model._default_manager.get_by_natural_key(*natural_key)
    parser.values.tenant = tenant


class TenantAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        tenant_model = get_tenant_model()
        tenant = tenant_model._default_manager.get_by_natural_key(*values)
        setattr(namespace, self.dest, tenant)


class Command(Command):
    # XXX: Remove when dropping support for Django 1.7
    if django.VERSION < (1, 8):
        args = 'tenant natural key'
    help = 'Used to create a specific tenant superuser.'
    requires_system_checks = False

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)
        if not isinstance(self.UserModel, TenantModelBase):
            raise CommandError(
                "The defined user model (%s) is not tenant specific." % self.UserModel._meta
            )

    def add_arguments(self, parser):
        super(Command, self).add_arguments(parser)
        parser.add_argument(
            'tenant', nargs='+', action=TenantAction,
            help='Specifies the tenant to use by natural key.'
        )

    def handle(self, *args, **options):
        try:
            tenant = options['tenant']
        except KeyError:
            # XXX: Remove when dropping support for Django 1.7
            tenant_model = get_tenant_model()
            tenant = tenant_model._default_manager.get_by_natural_key(*args)
        self.UserModel = self.UserModel.for_tenant(tenant)
        return super(Command, self).handle(*args, **options)
