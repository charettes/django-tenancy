from __future__ import unicode_literals

from django.db import models
from django.forms.models import modelform_factory

from ..models import Tenant
from ..views import SingleTenantObjectMixin, TenantModelFormMixin

from .forms import SpecificModelForm
from .models import RelatedSpecificModel, SpecificModel


def raise_exception(request):
    raise Exception(request.tenant.name)


class TenancyTestMixin(object):
    def get_tenant(self):
        return Tenant.objects.get(name='tenant')


# Classes used by SingleTenantObjectMixinTest
class MissingModelMixin(SingleTenantObjectMixin):
    pass


class InvalidModelMixin(SingleTenantObjectMixin):
    model = models.Model


class SpecificModelMixin(TenancyTestMixin, SingleTenantObjectMixin):
    model = SpecificModel


# Classes used by TenantModelFormMixinTest
class UnspecifiedFormClass(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel


class NonTenantModelFormClass(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = modelform_factory(Tenant)


class InvalidModelFormClass(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = modelform_factory(RelatedSpecificModel)


class SpecificModelFormMixin(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = SpecificModelForm
