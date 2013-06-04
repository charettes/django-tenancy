from __future__ import unicode_literals
import logging

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ... import get_tenant_model


class CommandLoggingHandler(logging.StreamHandler):
    VERBOSITY_LEVELS = {
        0: logging.ERROR,
        1: logging.INFO,  # Would like to use WARNING here but 1 is the default
        2: logging.INFO,  # verbosity level and should map to INFO.
        3: logging.DEBUG,
    }

    def __init__(self, stdout, stderr, verbosity=1):
        self.error_stream = logging.StreamHandler(stderr)
        # TODO: Use super when support for Python 2.6 is dropped
        logging.StreamHandler.__init__(self, stdout)
        self.setLevel(self.VERBOSITY_LEVELS[verbosity])

    def emit(self, record):
        if record.levelno >= logging.ERROR:
            self.error_stream.emit(record)
        else:
            # TODO: Use super when support for Python 2.6 is dropped
            logging.StreamHandler.emit(self, record)


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
        tenant.save(force_insert=True)

        # Remove the handler associated with the schema creation logger.
        logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)

        from ...settings import TENANT_AUTH_USER_MODEL
        if options.get('interactive', True) and TENANT_AUTH_USER_MODEL:
            confirm = raw_input(
                "\nYou just created a new tenant, which means you don't have "
                "any superusers defined.\nWould you like to create one "
                "now? (yes/no): "
            )
            while True:
                if confirm not in ('yes', 'no'):
                    confirm = raw_input('Please enter either "yes" or "no": ')
                elif confirm == 'yes':
                    call_command('createsuperuser', tenant=tenant, **options)
                    break
