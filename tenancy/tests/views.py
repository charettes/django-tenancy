from __future__ import unicode_literals

from django.db import models

from ..models import Tenant
from ..views import SingleTenantObjectMixin

from .models import SpecificModel


class MissingModelMixin(SingleTenantObjectMixin):
    pass


class InvalidModelMixin(SingleTenantObjectMixin):
    model = models.Model


class SpecificModelMixin(SingleTenantObjectMixin):
    model = SpecificModel

    def get_tenant(self):
        return Tenant.objects.get(name='tenant')