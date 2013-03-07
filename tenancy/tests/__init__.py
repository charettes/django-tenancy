from __future__ import  unicode_literals

import django
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test.testcases import TransactionTestCase
from django.test.utils import override_settings

from .. import get_tenant_model
from ..models import Tenant, TenantModelBase
from ..views import SingleTenantObjectMixin

from .models import *
from .utils import skipIfCustomTenant, TenancyTestCase


class TenantTest(TransactionTestCase):
    def assertSwapFailure(self, tenant_model, expected_message):
        with self.settings(TENANCY_TENANT_MODEL=tenant_model):
            with self.assertRaisesMessage(ImproperlyConfigured, expected_message):
                get_tenant_model()

    def test_swap_failures(self):
        """
        Make sure tenant swap failures raise the correct exception
        """
        self.assertSwapFailure(
            'invalid',
            "TENANCY_TENANT_MODEL must be of the form 'app_label.model_name'"
        )
        self.assertSwapFailure(
            'not.Installed',
            "TENANCY_TENANT_MODEL refers to model 'not.Installed' that has not been installed"
        )
        self.assertSwapFailure(
            'contenttypes.ContentType',
            "TENANCY_TENANT_MODEL refers to models 'contenttypes.ContentType' which is not a subclass of 'tenancy.AbstractTenant'"
        )

    @skipIfCustomTenant
    def test_content_types_deleted(self):
        """
        Make sure content types of tenant models are deleted upon their related
        tenant deletion.
        """
        tenant = Tenant.objects.create(name='tenant')
        model = tenant.specificmodels.model
        content_type = ContentType.objects.get_for_model(model)
        tenant.delete()
        self.assertFalse(ContentType.objects.filter(pk=content_type.pk).exists())


class TenantModelBaseTest(TenancyTestCase):
    def test_instancecheck(self):
        instance = self.tenant.specificmodels.create()
        self.assertIsInstance(instance, SpecificModel)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertIsInstance(instance, models.Model)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def assertIsSubclass(self, cls, base):
        self.assertTrue(issubclass(cls, base))

    def assertIsNotSubclass(self, cls, base):
        self.assertFalse(issubclass(cls, base))

    def test_subclasscheck(self):
        tenant_specific_model = self.tenant.specificmodels.model
        self.assertIsSubclass(tenant_specific_model, AbstractTenantModel)
        self.assertIsSubclass(tenant_specific_model, SpecificModel)
        self.assertIsNotSubclass(tenant_specific_model, RelatedSpecificModel)
        self.assertIsNotSubclass(tenant_specific_model, tuple)
        self.assertIsSubclass(tenant_specific_model, models.Model)
        tenant_specific_model_subclass = self.tenant.specific_models_subclasses.model
        self.assertIsSubclass(tenant_specific_model_subclass, SpecificModel)
        self.assertIsSubclass(tenant_specific_model_subclass, tenant_specific_model)


class TenantModelDescriptorTest(TenancyTestCase):
    def test_related_name(self):
        """
        Make sure the descriptor is correctly attached to the Tenant model
        when the related_name is specified or not.
        """
        self.assertEqual(
            Tenant.specificmodels.opts,
            SpecificModel._meta
        )
        self.assertEqual(
            Tenant.related_specific_models.opts,
            RelatedSpecificModel._meta
        )

    def test_model_class_cached(self):
        """
        Make sure the content type associated with the returned model is
        always created.
        """
        opts = self.tenant.specificmodels.model._meta
        self.assertTrue(
            ContentType.objects.filter(
                app_label=opts.app_label,
                model=opts.module_name
            ).exists()
        )


class TenantModelTest(TenancyTestCase):
    def test_isolation_between_tenants(self):
        """
        Make sure instances created in a tenant specific schema are not
        shared between tenants.
        """
        self.tenant.related_specific_models.create()
        self.assertEqual(self.other_tenant.related_specific_models.count(), 0)
        self.other_tenant.related_specific_models.create()
        self.assertEqual(self.tenant.related_specific_models.count(), 1)

    def test_foreign_key_between_tenant_models(self):
        """
        Make sure foreign keys between TenantModels work correctly.
        """
        for tenant in Tenant.objects.all():
            # Test object creation
            specific = tenant.specificmodels.create()
            related = tenant.related_tenant_models.create(fk=specific)
            # Test reverse related manager
            self.assertEqual(specific.fks.get(), related)
            # Test reverse filtering
            self.assertEqual(tenant.specificmodels.filter(fks=related).get(), specific)

    def test_m2m_between_tenant_models(self):
        """
        Make sure m2m between TenantModels work correctly.
        """
        for tenant in Tenant.objects.all():
            # Test object creation
            related = tenant.related_tenant_models.create()
            specific_model = related.m2m.create()
            # Test reverse related manager
            self.assertEqual(specific_model.m2ms.get(), related)
            # Test reverse filtering
            self.assertEqual(tenant.specificmodels.filter(m2ms=related).get(), specific_model)

    def test_subclassing(self):
        """
        Make sure tenant model subclasses share the same tenant.
        """
        for tenant in Tenant.objects.all():
            parents = tenant.specific_models_subclasses.model._meta.parents
            for parent in parents:
                if isinstance(parent, TenantModelBase):
                    self.assertEqual(parent.tenant, tenant)
            tenant.specific_models_subclasses.create()
            self.assertEqual(tenant.specificmodels.count(), 1)

    def test_signals(self):
        """
        Make sure signals are correctly dispatched for tenant models
        """
        for tenant in Tenant.objects.all():
            signal_model = tenant.signal_models.model
            instance = signal_model()
            instance.save()
            instance.delete()
            self.assertListEqual(
                signal_model.logs(),
                [
                 models.signals.pre_init,
                 models.signals.post_init,
                 models.signals.pre_save,
                 models.signals.post_save,
                 models.signals.pre_delete,
                 models.signals.post_delete
                 ]
            )


# TODO: Remove when support for django 1.4 is dropped
class raise_cmd_error_stderr(object):
    def write(self, msg):
        raise CommandError(msg)


@skipIfCustomTenant
class CreateTenantCommandTest(TransactionTestCase):
    stderr = raise_cmd_error_stderr()

    def create_tenant(self, *args, **kwargs):
        if django.VERSION[:2] == (1, 4):
            kwargs['stderr'] = self.stderr
        call_command('create_tenant', *args, **kwargs)

    def test_too_many_fields(self):
        args = ('name', 'useless')
        expected_message = (
            "Number of args exceeds the number of fields for model tenancy.Tenant.\n"
            "Got %s when defined fields are ('name',)." % repr(args)
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            self.create_tenant(*args)

    def test_full_clean_failure(self):
        expected_message = (
            'Invalid value for field "name": This field cannot be blank.'
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            self.create_tenant()

    def test_success(self):
        self.create_tenant('tenant')
        Tenant.objects.get(name='tenant').delete()


@override_settings(
    ROOT_URLCONF='tenancy.tests.urls',
    MIDDLEWARE_CLASSES=('tenancy.tests.middleware.TenantMiddleware',))
class SingleTenantObjectMixinTest(TenancyTestCase):
    def test_improperly_configured(self):
        with self.assertRaisesMessage(ImproperlyConfigured,
            'MissingModelView is missing a model.'):
            self.client.get('/missing-model')
        with self.assertRaisesMessage(ImproperlyConfigured,
            'InvalidModelView.model is not an instance of TenantModelBase.'):
            self.client.get('/invalid-model')

    def test_get_object(self):
        specific_model = self.tenant.specificmodels.create()
        response = self.client.get("/specific-model/%s" % specific_model.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            specific_model,
            next(serializers.deserialize('json', response.content)).object
        )