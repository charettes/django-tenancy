from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

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

app_label, model_name = settings.AUTH_USER_MODEL.split('.')
lazy_class_prepared(app_label, model_name, is_tenant_user_model)


HOST_NAME = getattr(
    settings, 'TENANCY_HOST_NAME', 'tenant'
)

SCHEMA_AUTHORIZATION = getattr(
    settings, 'TENANCY_SCHEMA_AUTHORIZATION', False
)
