from __future__ import unicode_literals
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError

from ... import get_tenant_model


class Command(BaseCommand):
    logger = logging.getLogger('tenancy.management.create_tenant_schema')
    verbosity_logging_levels = {
        0: logging.NOTSET,
        1: logging.INFO,
        2: logging.INFO,
        3: logging.DEBUG,
    }

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

        # Redirect the output of the schema creation logger to our stdout.
        verbosity = int(options['verbosity'])
        handler = logging.StreamHandler(self.stdout)
        self.logger.setLevel(self.verbosity_logging_levels[verbosity])
        self.logger.addHandler(handler)

        # Create the tenant instance and create tables
        with transaction.commit_on_success():
            tenant.save(force_insert=True)

        # Remove the handler associated with the schema creation logger.
        self.logger.removeHandler(handler)
        self.logger.setLevel(logging.NOTSET)
