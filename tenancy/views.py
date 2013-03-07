from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.views.generic.detail import SingleObjectMixin

from .models import TenantModelBase


class TenantMixin(object):
    """
    View mixin that retrieve the current tenant from the request. This could
    have been set from a middleware base on a domain name for example.
    """

    def get_tenant(self):
        return self.request.tenant


class SingleTenantObjectMixin(TenantMixin, SingleObjectMixin):
    """
    View mixin that returns the correct queryset for the specified model based
    on the retrieved tenant.
    """

    def get_queryset(self):
        if self.model:
            if not isinstance(self.model, TenantModelBase):
                msg = "%s.model is not an instance of TenantModelBase."
                raise ImproperlyConfigured(msg % self.__class__.__name__)
            tenant = self.get_tenant()
            related_name = self.model._tenant_meta.related_name
            return getattr(tenant, related_name).all()
        raise ImproperlyConfigured("%s is missing a model." %
                                   self.__class__.__name__)