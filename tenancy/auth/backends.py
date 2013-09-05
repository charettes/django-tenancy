from __future__ import unicode_literals

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from .. import get_tenant_model
from ..models import TenantModelBase


class CustomTenantUserBackend(object):
    def __init__(self):
        user_model = get_user_model()
        if not isinstance(user_model, TenantModelBase):
            raise ImproperlyConfigured(
                "The `tenancy.auth.backends.CustomTenantUserBackend` "
                "authentification backend can only be used with a custom "
                "tenant user model."
            )
        tenant_model = get_tenant_model()
        attr_name = tenant_model.ATTR_NAME
        try:
            tenant = getattr(connection, attr_name)
        except AttributeError:
            raise ImproperlyConfigured(
                "The `tenancy.auth.backends.CustomTenantUserBackend` "
                "authentification backend requires that a `%s` attribute "
                "be set on the default connection to work properly. The "
                "`tenancy.middleware.GlobalTenantMiddleware` does "
                "just that." % attr_name
            )
        self.tenant_user_model = user_model.for_tenant(tenant)

    def authenticate(self, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(self.tenant_user_model.USERNAME_FIELD)
        try:
            user = self.tenant_user_model._default_manager.get_by_natural_key(username)
            if user.check_password(password):
                return user
        except self.tenant_user_model.DoesNotExist:
            return None

    def get_user(self, pk):
        try:
            return self.tenant_user_model._default_manager.get(pk=pk)
        except self.tenant_user_model.DoesNotExist:
            return None
