from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

TENANT_MODEL = getattr(settings, 'TENANCY_TENANT_MODEL', 'tenancy.Tenant')

try:
    app_label, model_name = TENANT_MODEL.split('.')
except ValueError:
    raise ImproperlyConfigured(
        "TENANCY_TENANT_MODEL must be of the form 'app_label.model_name'"
    )

HOST_NAME = getattr(settings, 'TENANCY_HOST_NAME', 'tenant')

SCHEMA_AUTHORIZATION = getattr(settings, 'TENANCY_SCHEMA_AUTHORIZATION', False)
