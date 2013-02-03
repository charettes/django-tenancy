from __future__ import unicode_literals

from django.conf import settings

DEFAULT_TENANT_MODEL = 'tenancy.Tenant'
TENANT_MODEL = getattr(settings, 'TENANCY_TENANT_MODEL', DEFAULT_TENANT_MODEL)