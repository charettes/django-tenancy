from __future__ import unicode_literals

from django.contrib.auth import models as auth_app
from django.contrib.auth.management import create_superuser
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models.signals import post_syncdb

from .signals import lazy_class_prepared


DEFAULT_TENANT_MODEL = 'tenancy.Tenant'

TENANT_MODEL = getattr(
    settings, 'TENANCY_TENANT_MODEL', DEFAULT_TENANT_MODEL
)

try:
    app_label, model_name = TENANT_MODEL.split('.')
except ValueError:
    raise ImproperlyConfigured(
        "TENANCY_TENANT_MODEL must be of the form 'app_label.model_name'"
    )

TENANT_AUTH_USER_MODEL = False


def is_tenant_user_model(sender):
    from .models import TenantModelBase
    if isinstance(sender, TenantModelBase):
        global TENANT_AUTH_USER_MODEL
        TENANT_AUTH_USER_MODEL = True
        # Disconnect the `create_superuser` post-syncdb signal receiver
        # since the swapped for user model is tenant specific
        post_syncdb.disconnect(
            create_superuser,
            sender=auth_app,
            dispatch_uid='django.contrib.auth.management.create_superuser'
        )
    else:
        # Make sure the `create_superuser` signal is correctly attached
        # since this module might be reloaded during testing
        post_syncdb.connect(
            create_superuser,
            sender=auth_app,
            dispatch_uid='django.contrib.auth.management.create_superuser',
        )
app_label, model_name = settings.AUTH_USER_MODEL.split('.')
lazy_class_prepared(app_label, model_name, is_tenant_user_model)
