from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured

from .forms import (RelatedInlineFormSet, RelatedTenantModelForm,
    SpecificModelForm, SpecificModelFormSet)
from .models import RelatedTenantModel, SpecificModel
from .views import (InvalidModelMixin, MissingModelFormMixin,
    MissingModelMixin, NonModelFormMixin, NonTenantModelFormClass,
    RelatedInlineFormSetMixin, SpecificModelFormMixin,
    SpecificModelFormSetMixin, SpecificModelMixin, TenantWizardView,
    UnspecifiedFormClass)
from .utils import TenancyTestCase


class TenantObjectMixinTest(TenancyTestCase):
    def test_missing_model(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            'MissingModelMixin is missing a model.',
            MissingModelMixin().get_model
        )

    def test_invalid_model(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            'InvalidModelMixin.model is not an instance of TenantModelBase.',
            InvalidModelMixin().get_model
        )

    def test_get_queryset(self):
        specific_model = self.tenant.specificmodels.create()
        self.assertEqual(
            specific_model,
            SpecificModelMixin().get_queryset().get()
        )

    def test_get_template_names(self):
        self.assertIn(
            'tenancy/specificmodel.html',
            SpecificModelMixin().get_template_names()
        )


class TenantModelFormMixinTest(TenancyTestCase):
    def test_unspecified_form_class(self):
        """
        When no `form_class` is specified, `get_form_class` should behave just
        like `ModelFormMixin.get_form_class`.
        """
        self.assertEqual(
            SpecificModel.for_tenant(self.tenant),
            UnspecifiedFormClass().get_form_class()._meta.model
        )

    def test_missing_model_form(self):
        """
        Specified `ModelForm` subclass attached to no models should be
        working correctly.
        """
        self.assertEqual(
            SpecificModel.for_tenant(self.tenant),
            MissingModelFormMixin().get_form_class()._meta.model
        )

    def test_invalid_form_class_model(self):
        """
        If the specified `form_class` is not a subclass of `ModelForm` or
        `BaseModelFormSet` or it's declared model is not and instance of
        `TenantModelBase` an `ImproperlyConfigured` exception should be raised.
        """
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "NonModelFormMixin.form_class must be a subclass of `ModelForm` "
            "or `BaseModelFormSet`.",
            NonModelFormMixin().get_form_class
        )
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "NonTenantModelFormClass.form_class' model is not an "
            "instance of TenantModelBase.",
            NonTenantModelFormClass().get_form_class
        )

    def test_get_modelform_class(self):
        form_class = SpecificModelFormMixin().get_form_class()
        self.assertTrue(issubclass(form_class, SpecificModelForm))
        self.assertEqual(
            form_class._meta.model,
            self.tenant.specificmodels.model
        )

    def test_get_modelformset_class(self):
        formset_class = SpecificModelFormSetMixin().get_form_class()
        self.assertTrue(issubclass(formset_class, SpecificModelFormSet))
        model = SpecificModel.for_tenant(self.tenant)
        self.assertEqual(formset_class.model, model)
        form_class = formset_class.form
        self.assertTrue(issubclass(form_class, SpecificModelForm))
        self.assertEqual(form_class._meta.model, model)

    def test_get_inlineformset_class(self):
        formset_class = RelatedInlineFormSetMixin().get_form_class()
        self.assertTrue(issubclass(formset_class, RelatedInlineFormSet))
        model = RelatedTenantModel.for_tenant(self.tenant)
        self.assertEqual(formset_class.model, model)
        self.assertEqual(formset_class.fk, model._meta.get_field('fk'))
        form_class = formset_class.form
        self.assertTrue(issubclass(form_class, RelatedTenantModelForm))
        self.assertEqual(form_class._meta.model, model)


class TenantWizardMixinTest(TenancyTestCase):
    def create_wizard(self):
        return TenantWizardView(**TenantWizardView.get_initkwargs())

    def test_model_form(self):
        wizard = self.create_wizard()
        form = wizard.get_form('tenant_model_form')
        self.assertIsInstance(form, SpecificModelForm)
        self.assertEqual(
            form._meta.model, SpecificModel.for_tenant(self.tenant)
        )

    def test_model_formset(self):
        wizard = self.create_wizard()
        formset = wizard.get_form('tenant_model_formset')
        self.assertIsInstance(formset, SpecificModelFormSet)
        self.assertEqual(
            formset.model, SpecificModel.for_tenant(self.tenant)
        )
        self.assertTrue(issubclass(formset.form, SpecificModelForm))

    def test_inline_formset(self):
        wizard = self.create_wizard()
        formset = wizard.get_form('tenant_inline_formset')
        self.assertIsInstance(formset, RelatedInlineFormSet)
        model = RelatedTenantModel.for_tenant(self.tenant)
        self.assertEqual(formset.model, model)
        self.assertEqual(formset.fk, model._meta.get_field('fk'))
        self.assertTrue(issubclass(formset.form, RelatedTenantModelForm))
