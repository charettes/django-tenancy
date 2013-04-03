from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured

from .forms import SpecificModelForm
from .views import (InvalidModelFormClass, InvalidModelMixin,
    MissingModelMixin, NonTenantModelFormClass, SpecificModelMixin,
    SpecificModelFormMixin, UnspecifiedFormClass)
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
            self.tenant.specificmodels.model,
            UnspecifiedFormClass().get_form_class()._meta.model
        )

    def test_invalid_form_class_model(self):
        """
        If the specified `form_class`' model is not and instance of
        TenantModelBase or is not in the mro of the view's model an
        `ImpropelyConfigured` error should be raised.
        """
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "NonTenantModelFormClass.form_class' model is not an "
            "instance of TenantModelBase.",
            NonTenantModelFormClass().get_form_class
        )
        self.assertRaisesMessage(
            ImproperlyConfigured,
            "InvalidModelFormClass's model: %s, is not a subclass "
            "of it's `form_class` model: RelatedSpecificModel." %
            self.tenant.specificmodels.model.__name__,
            InvalidModelFormClass().get_form_class
        )

    def test_get_form_class(self):
        form_class = SpecificModelFormMixin().get_form_class()
        self.assertTrue(issubclass(form_class, SpecificModelForm))
        self.assertEqual(
            form_class._meta.model,
            self.tenant.specificmodels.model
        )
