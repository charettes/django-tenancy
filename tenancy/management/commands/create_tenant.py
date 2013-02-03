from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError

from ... import get_tenant_model


class Command(BaseCommand):
    def handle(self, *args, **options):
        tenant_model = get_tenant_model()
        # Attempt to build the instance based on specified data
        try:
            tenant = tenant_model(None, *args)
        except IndexError:
            opts = tenant_model._meta
            field_names = tuple(
                field.name for field in opts.local_fields if not field.primary_key
            )
            raise CommandError(
                "Number of args exceeds the number of fields for model %s.%s.\n"
                "Got %s when defined fields are %s." % (
                    opts.app_label,
                    opts.object_name,
                    args,
                    field_names
                )
            )
        # Full clean the instance
        try:
            tenant.full_clean()
        except ValidationError as e:
            name, messages = e.message_dict.items()[0]
            raise CommandError(
                'Invalid value for field "%s": %s.' % (name, messages[0])
            )
        # Create the tenant instance and create tables
        with transaction.commit_on_success():
            tenant.save(force_insert=True)