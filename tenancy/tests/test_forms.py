from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured

from ..forms import (tenant_inlineformset_factory, tenant_modelform_factory,
    tenant_modelformset_factory)
from ..models import Tenant

from .models import NonTenantModel, RelatedTenantModel, SpecificModel
from .utils import TenancyTestCase


class TenantModelFormFactoryTest(TenancyTestCase):
    def test_non_tenant_model(self):
        with self.assertRaisesMessage(
                ImproperlyConfigured,
                'Tenant must be an instance of TenantModelBase'):
            tenant_modelform_factory(self.tenant, Tenant)

    def test_valid_modelform(self):
        form = tenant_modelform_factory(self.tenant, SpecificModel)
        self.assertEqual(form._meta.model, self.tenant.specificmodels.model)
        self.assertIn('date', form.base_fields)
        self.assertIn('non_tenant', form.base_fields)


class TenantModelFormsetFactoryTest(TenancyTestCase):
    def test_non_tenant_model(self):
        with self.assertRaisesMessage(
                ImproperlyConfigured,
                'Tenant must be an instance of TenantModelBase'):
            tenant_modelformset_factory(self.tenant, Tenant)

    def test_valid_modelform(self):
        formset = tenant_modelformset_factory(self.tenant, SpecificModel)
        self.assertEqual(formset.model, self.tenant.specificmodels.model)
        form = formset.form
        self.assertIn('date', form.base_fields)
        self.assertIn('non_tenant', form.base_fields)


class TenantInlineFormsetFactoryTest(TenancyTestCase):
    def test_non_tenant_parent_model(self):
        """
        Non-tenant `parent_model` should be allowed.
        """
        formset = tenant_inlineformset_factory(
            self.tenant,
            NonTenantModel,
            SpecificModel,
            fk_name='non_tenant'
        )
        tenant_specific_model = self.tenant.specificmodels.model
        self.assertEqual(formset.model, tenant_specific_model)
        non_tenant_fk = tenant_specific_model._meta.get_field('non_tenant')
        self.assertEqual(non_tenant_fk, formset.fk)

    def test_non_tenant_model(self):
        with self.assertRaisesMessage(
                ImproperlyConfigured,
                'Tenant must be an instance of TenantModelBase'):
            tenant_inlineformset_factory(self.tenant, Tenant, Tenant)

    def test_valid_inlineformset(self):
        formset = tenant_inlineformset_factory(
            self.tenant,
            SpecificModel,
            RelatedTenantModel
        )
        tenant_related_model = self.tenant.related_tenant_models.model
        self.assertEqual(formset.model, tenant_related_model)
        fk = tenant_related_model._meta.get_field('fk')
        self.assertEqual(fk, formset.fk)