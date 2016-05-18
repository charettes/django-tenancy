from __future__ import unicode_literals

import warnings

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured

from .. import get_tenant_model
from ..models import TenantModelBase


class TenantUserBackend(object):
    def __init__(self):
        self.user_model = get_user_model()
        self.tenant_model = get_tenant_model()
        if not isinstance(self.user_model, TenantModelBase):
            raise ImproperlyConfigured(
                "The `tenancy.auth.backends.TenantUserBackend` "
                "authentification backend can only be used with a custom "
                "tenant user model."
            )

    def get_tenant_user_model(self, tenant=None):
        if tenant is None:
            tenant = self.tenant_model.get_global()
            if tenant is None:
                return None
        return self.user_model.for_tenant(tenant)

    def get_tenant_user_queryset(self, tenant_user_model):
        return tenant_user_model._default_manager

    def authenticate(self, username=None, password=None, tenant=None, **kwargs):
        if tenant is None:
            tenant = kwargs.get(self.tenant_model.ATTR_NAME)
        tenant_user_model = self.get_tenant_user_model(tenant)
        if tenant_user_model is None:
            return None
        users = self.get_tenant_user_queryset(tenant_user_model)
        username_field = tenant_user_model.USERNAME_FIELD
        if username is None:
            username = kwargs.get(username_field)
        try:
            user = users.get(**{username_field: username})
        except tenant_user_model.DoesNotExist:
            return None
        if user.check_password(password):
            return user

    def get_user(self, pk):
        tenant_user_model = self.get_tenant_user_model()
        if tenant_user_model is None:
            return None
        users = self.get_tenant_user_queryset(tenant_user_model)
        try:
            return users.get(pk=pk)
        except tenant_user_model.DoesNotExist:
            return None


class CustomTenantUserBackend(TenantUserBackend):
    def __init__(self):
        warnings.warn('CustomTenantUserBackend is deprecated in favor or TenantUserBackend.', DeprecationWarning)
        super(CustomTenantUserBackend, self).__init__()
