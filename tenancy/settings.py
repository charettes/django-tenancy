from __future__ import unicode_literals

from django.conf import settings


TENANT_MODEL = getattr(settings, 'TENANCY_TENANT_MODEL', 'tenancy.Tenant')