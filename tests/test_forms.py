from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.forms.models import modelform_factory, modelformset_factory

from tenancy.compat import get_remote_field_model
from tenancy.forms import (
    tenant_inlineformset_factory, tenant_modelform_factory,
    tenant_modelformset_factory,
)
from tenancy.models import Tenant

from .forms import (
    NonTenantInlineFormSet, RelatedInlineFormSet, RelatedTenantModelForm,
    SpecificModelForm, SpecificModelFormSet,
)
from .models import NonTenantModel, RelatedTenantModel, SpecificModel
from .utils import TenancyTestCase


class TenantModelFormFactoryTest(TenancyTestCase):
    def test_non_tenant_model(self):
        form = modelform_factory(Tenant, fields=['name'])
        with self.assertRaisesMessage(
                ImproperlyConfigured,
                'Tenant must be an instance of TenantModelBase'):
            tenant_modelform_factory(self.tenant, form)

    def test_valid_modelform(self):
        form = tenant_modelform_factory(self.tenant, SpecificModelForm)
        self.assertEqual(
            form._meta.model, SpecificModel.for_tenant(self.tenant)
        )
        self.assertTrue(issubclass(form, SpecificModelForm))
        self.assertIn('date', form.base_fields)


class TenantModelFormsetFactoryTest(TenancyTestCase):
    def test_non_tenant_model(self):
        formset = modelformset_factory(Tenant, fields=['name'])
        with self.assertRaisesMessage(
                ImproperlyConfigured,
                'Tenant must be an instance of TenantModelBase'):
            tenant_modelformset_factory(self.tenant, formset)

    def test_valid_modelformset(self):
        formset = tenant_modelformset_factory(self.tenant, SpecificModelFormSet)
        tenant_specific_model = SpecificModel.for_tenant(self.tenant)
        self.assertEqual(formset.model, tenant_specific_model)
        self.assertTrue(issubclass(formset, SpecificModelFormSet))
        form = formset.form
        self.assertTrue(issubclass(form, SpecificModelForm))
        self.assertEqual(tenant_specific_model, form._meta.model)


class TenantInlineFormsetFactoryTest(TenancyTestCase):
    def test_valid_nontenant_parent_inlineformset(self):
        formset = tenant_inlineformset_factory(self.tenant, NonTenantInlineFormSet)
        tenant_specific_model = SpecificModel.for_tenant(self.tenant)
        self.assertEqual(formset.model, tenant_specific_model)
        self.assertEqual(get_remote_field_model(formset.fk), NonTenantModel)
        self.assertTrue(issubclass(formset, NonTenantInlineFormSet))
        form = formset.form
        self.assertTrue(issubclass(form, SpecificModelForm))
        self.assertEqual(tenant_specific_model, form._meta.model)

    def test_valid_inlineformset(self):
        formset = tenant_inlineformset_factory(self.tenant, RelatedInlineFormSet)
        tenant_specific_model = SpecificModel.for_tenant(self.tenant)
        tenant_related_model = RelatedTenantModel.for_tenant(self.tenant)
        self.assertEqual(formset.model, tenant_related_model)
        self.assertEqual(get_remote_field_model(formset.fk), tenant_specific_model)
        self.assertTrue(issubclass(formset, RelatedInlineFormSet))
        form = formset.form
        self.assertTrue(issubclass(form, RelatedTenantModelForm))
        self.assertEqual(tenant_related_model, form._meta.model)
