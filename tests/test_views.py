from __future__ import unicode_literals

import warnings
from unittest import skipUnless

import django
from django.core.exceptions import ImproperlyConfigured
from django.test.client import RequestFactory
from django.test.utils import override_settings

from .forms import (
    RelatedInlineFormSet, RelatedTenantModelForm, SpecificModelForm,
    SpecificModelFormSet,
)
from .models import RelatedTenantModel, SpecificModel
from .utils import TenancyTestCase
from .views import (
    InvalidModelMixin, MissingFieldsModelFormMixin, MissingModelFormMixin,
    MissingModelMixin, NonModelFormMixin, NonTenantModelFormClass,
    RelatedInlineFormSetMixin, SpecificModelFormMixin,
    SpecificModelFormSetMixin, SpecificModelMixin, TenantMixinView,
    UnspecifiedFormClass,
)

try:
    from .views import TenantWizardView
except ImportError:
    TenantWizardView = None


@override_settings(ROOT_URLCONF='tests.urls')
class TenantMixinTest(TenancyTestCase):
    client_class = RequestFactory

    def test_get_tenant(self):
        view = TenantMixinView()
        request = self.client.request()
        setattr(request, view.tenant_attr_name, self.tenant)
        view.request = request
        self.assertEqual(view.get_tenant(), self.tenant)

    def test_tenant_attr(self):
        view = TenantMixinView()
        request = self.client.request()
        attr_name = view.tenant_attr_name
        setattr(request, attr_name, self.tenant)
        view.request = request
        self.assertEqual(getattr(view, attr_name), self.tenant)


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
            'tests/specificmodel.html',
            SpecificModelMixin().get_template_names()
        )

    def test_get_context_object_name(self):
        self.assertEqual(
            SpecificModelMixin().get_context_object_name(
                self.tenant.specificmodels.create()
            ), 'specificmodel'
        )
        self.assertEqual(
            SpecificModelMixin().get_context_object_name(
                self.tenant.specificmodels
            ), 'specificmodel_list'
        )
        self.assertEqual(
            SpecificModelMixin().get_context_object_name(
                self.tenant.specificmodels.all()
            ), 'specificmodel_list'
        )
        mixin = SpecificModelMixin()
        mixin.context_object_name = 'test'
        self.assertEqual(
            mixin.get_context_object_name(None), mixin.context_object_name
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

    @skipUnless(
        django.VERSION < (1, 8),
        'Missing `fields` warnings are only raised on Django < 1.8'
    )
    def test_missing_fields_warning(self):
        """
        Since `TenantModelFormMixin` is meant to override `ModelFormMixin`
        make sure to mimic the raised warnings when no `fields` are specified.
        """
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter('always')
            MissingFieldsModelFormMixin().get_form_class()
        self.assertTrue(records)
        warning = records[0]
        self.assertEqual(warning.category, DeprecationWarning)
        self.assertEqual(
            str(warning.message),
            "Using TenantModelFormMixin (base class of MissingFieldsModelFormMixin) "
            "without the 'fields' attribute is deprecated."
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


@skipUnless(TenantWizardView, 'Missing formtools.')
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
