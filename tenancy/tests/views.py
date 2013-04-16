from __future__ import unicode_literals

from django.contrib.formtools.wizard.views import NamedUrlWizardView
from django.db import models
from django.forms.models import modelform_factory

from ..models import Tenant
from ..views import TenantObjectMixin, TenantModelFormMixin, TenantWizardMixin

from .forms import (RelatedInlineFormSet, SpecificModelForm,
    SpecificModelFormSet)
from .models import RelatedTenantModel, SpecificModel


def raise_exception(request):
    raise Exception(request.tenant.name)


class TenancyTestMixin(object):
    def get_tenant(self):
        return Tenant.objects.get(name='tenant')


# Classes used by SingleTenantObjectMixinTest
class MissingModelMixin(TenantObjectMixin):
    pass


class InvalidModelMixin(TenantObjectMixin):
    model = models.Model


class SpecificModelMixin(TenancyTestMixin, TenantObjectMixin):
    model = SpecificModel


# Classes used by TenantModelFormMixinTest
class UnspecifiedFormClass(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel


class NonTenantModelFormClass(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = modelform_factory(Tenant)


class SpecificModelFormMixin(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = SpecificModelForm


class SpecificModelFormSetMixin(TenancyTestMixin, TenantModelFormMixin):
    model = SpecificModel
    form_class = SpecificModelFormSet


class RelatedInlineFormSetMixin(TenancyTestMixin, TenantModelFormMixin):
    model = RelatedTenantModel
    form_class = RelatedInlineFormSet


# Class used by TenantWizardMixinTest
class TenantWizardView(TenancyTestMixin, TenantWizardMixin,
                       NamedUrlWizardView):
    @classmethod
    def get_initkwargs(cls, *args, **kwargs):
        form_list = (
            ('tenant_model_form', SpecificModelForm),
            ('tenant_model_formset', SpecificModelFormSet),
            ('tenant_inline_formset', RelatedInlineFormSet)
        )
        kwargs.setdefault('url_name', 'wizard')
        return super(TenantWizardView, cls).get_initkwargs(
            form_list, *args, **kwargs
        )
