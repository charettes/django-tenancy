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

TENANT_AUTH_USER_MODEL = False

try:
    from django.contrib.auth import get_user_model
except ImportError:
    HAS_CUSTOM_USER_SUPPORT = False
else:
    HAS_CUSTOM_USER_SUPPORT = True
    from .signals import LazyClassPrepared
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    def is_tenant_user_model(sender):
        from .models import TenantModelBase
        if isinstance(sender, TenantModelBase):
            global TENANT_AUTH_USER_MODEL
            TENANT_AUTH_USER_MODEL = True
    LazyClassPrepared(app_label, model_name, is_tenant_user_model)