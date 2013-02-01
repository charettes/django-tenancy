from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError

from ... import get_tenant_model


class Command(BaseCommand):
    def handle(self, *args, **options):
        # Attempt to build the instance based on specified args
        try:
            tenant = get_tenant_model()(pk=None, *args)
        except IndexError as e:
            raise CommandError(e)
        # Full clean the instance
        try:
            tenant.full_clean()
        except ValidationError as e:
            raise CommandError(e)
        # Create the tenant instance and create tables
        with transaction.commit_on_success():
            tenant.save(force_insert=True)