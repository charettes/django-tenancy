from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


DEFAULT_TENANT_MODEL = 'tenancy.Tenant'

TENANT_MODEL =  getattr(
    settings, 'TENANCY_TENANT_MODEL', DEFAULT_TENANT_MODEL
)

try:
    app_label, model_name = TENANT_MODEL.split('.')
except ValueError:
    raise ImproperlyConfigured(
        "TENANCY_TENANT_MODEL must be of the form 'app_label.model_name'"
    )
