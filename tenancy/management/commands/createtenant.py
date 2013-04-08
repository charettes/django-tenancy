from __future__ import unicode_literals
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError

from ... import get_tenant_model


class CommandLoggingHandler(logging.StreamHandler):
    VERBOSITY_LEVELS = {
        0: logging.NOTSET,
        1: logging.INFO,
        2: logging.INFO,
        3: logging.DEBUG,
    }

    def __init__(self, stdout, stderr, verbosity=1):
        self.error_stream = logging.StreamHandler(stderr)
        super(CommandLoggingHandler, self).__init__(stdout)
        self.setLevel(self.VERBOSITY_LEVELS[verbosity])

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.error_stream.emit(record)
        else:
            return super(CommandLoggingHandler, self).emit(record)


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

        # Redirect the output of the schema creation logger to our stdout.
        handler = CommandLoggingHandler(
            self.stdout, self.stderr, int(options['verbosity'])
        )
        logger = logging.getLogger('tenancy')
        logger.setLevel(handler.level)
        logger.addHandler(handler)

        # Create the tenant instance and create tables
        with transaction.commit_on_success():
            tenant.save(force_insert=True)

        # Remove the handler associated with the schema creation logger.
        logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)
