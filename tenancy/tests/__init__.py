from __future__ import  unicode_literals

import django
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test.testcases import TransactionTestCase
from django.utils.unittest.case import skipIf

from ..models import Tenant, TenantModelBase

from .models import *
from .utils import skipIfCustomTenant, TenancyTestCase


class TenantModelBaseTest(TenancyTestCase):
    def test_instancecheck(self):
        instance = self.tenant.specificmodels.create()
        self.assertIsInstance(instance, SpecificModel)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertIsInstance(instance, models.Model)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def test_subclasscheck(self):
        tenant_specific_model = self.tenant.specificmodels.model
        self.assertTrue(issubclass(tenant_specific_model, SpecificModel))
        self.assertFalse(issubclass(tenant_specific_model, RelatedSpecificModel))
        self.assertFalse(issubclass(tenant_specific_model, tuple))
        self.assertTrue(issubclass(tenant_specific_model, models.Model))
        tenant_specific_model_subclass = self.tenant.specific_models_subclasses.model
        self.assertTrue(issubclass(tenant_specific_model_subclass, SpecificModel))
        self.assertTrue(issubclass(tenant_specific_model_subclass, tenant_specific_model))


class TenantModelDescriptorTest(TenancyTestCase):
    def test_related_name(self):
        """
        Make sure the descriptor is correctly attached to the Tenant model
        when the related_name is specified or not.
        """
        self.assertEqual(
            self.tenant_model.specificmodels.opts,
            SpecificModel._meta
        )
        self.assertEqual(
            self.tenant_model.related_specific_models.opts,
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
        Make sure instances created in a tenant specific databases are not
        shared between tenants.
        """
        self.tenant.related_specific_models.create()
        self.assertEqual(self.other_tenant.related_specific_models.count(), 0)
        self.other_tenant.related_specific_models.create()
        self.assertEqual(self.tenant.related_specific_models.count(), 1)

    def test_foreign_key_between_tenant_models(self):
        """
        Make sure foreign keys to TenantModels work correctly.
        """
        for tenant in self.tenant_model.objects.all():
            # Test object creation
            specific_model = tenant.specificmodels.create()
            fk = tenant.fk_to_tenant_models.create(specific_model=specific_model)
            # Test reverse related manager
            self.assertEqual(specific_model.fks.get(), fk)
            # Test reverse filtering
            self.assertEqual(tenant.specificmodels.filter(fks=fk).get(), specific_model)

    def test_subclassing(self):
        """
        Make sure tenant model subclasses share the same tenant.
        """
        for tenant in self.tenant_model.objects.all():
            parents = tenant.specific_models_subclasses.model._meta.parents
            for parent in parents:
                if isinstance(parent, TenantModelBase):
                    self.assertEqual(parent.tenant, tenant)
            tenant.specific_models_subclasses.create()
            self.assertEqual(tenant.specificmodels.count(), 1)


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