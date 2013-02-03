from __future__ import  unicode_literals

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test.testcases import TransactionTestCase
from django.utils.unittest.case import skipIf

from .models import Tenant, TenantModel, TenantModelBase
from .settings import DEFAULT_TENANT_MODEL, TENANT_MODEL


def skipIfCustomTenant(skipped):
    return skipIf(TENANT_MODEL != DEFAULT_TENANT_MODEL, 'Custom tenant model in use')(skipped)


class BaseTenantTestCase(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='tenant')
        self.other_tenant = Tenant.objects.create(name='other_tenant')

    def tearDown(self):
        Tenant.objects.all().delete()


class SpecificModel(TenantModel):
    pass


class RelatedSpecificModel(TenantModel):
    class TenantMeta:
        related_name = 'related_specific_models'


class SpecificModelSubclass(SpecificModel):
    class TenantMeta:
        related_name = 'specific_models_subclasses'


class FkToTenantModel(TenantModel):
    specific_model = models.ForeignKey(SpecificModel, related_name='fks')

    class TenantMeta:
        related_name = 'fk_to_tenant_models'


class TenantModelBaseTest(BaseTenantTestCase):
    def test_instancecheck(self):
        instance = self.tenant.specificmodels.create()
        self.assertIsInstance(instance, SpecificModel)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertIsInstance(instance, models.Model)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def test_subclassheck(self):
        model = self.tenant.specificmodels.model
        self.assertTrue(issubclass(model, SpecificModel))
        self.assertFalse(issubclass(model, RelatedSpecificModel))


class TenantModelDescriptorTest(BaseTenantTestCase):
    def test_related_name(self):
        """
        Make sure the descriptor is correctly attached to the Tenant model
        when the related_name is specified or not.
        """
        self.assertEqual(Tenant.specificmodels.opts, SpecificModel._meta)
        self.assertEqual(Tenant.related_specific_models.opts,
                         RelatedSpecificModel._meta)

    def test_model_class_cached(self):
        """
        Make sure the content type associated with the returned model is
        always created.
        """
        opts = self.tenant.specificmodels.model._meta
        self.assertTrue(ContentType.objects.filter(app_label=opts.app_label,
                                                   model=opts.module_name).exists())


class TenantModelTest(BaseTenantTestCase):
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
        for tenant in Tenant.objects.all():
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
        for tenant in Tenant.objects.all():
            parents = tenant.specific_models_subclasses.model._meta.parents
            for parent in parents:
                if isinstance(parent, TenantModelBase):
                    self.assertEqual(parent.tenant, tenant)
            tenant.specific_models_subclasses.create()
            self.assertEqual(tenant.specificmodels.count(), 1)


@skipIfCustomTenant
class CreateTenantCommandTest(TransactionTestCase):
    def test_too_many_fields(self):
        args = ('name', 'useless')
        expected_message = (
            "Number of args exceeds the number of fields for model tenancy.Tenant.\n"
            "Got %s when defined fields are ('name',)." % repr(args)
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            call_command('create_tenant', *args)

    def test_full_clean_failure(self):
        expected_message = (
            'Invalid value for field "name": This field cannot be blank.'
        )
        with self.assertRaisesMessage(CommandError, expected_message):
            call_command('create_tenant')

    def test_success(self):
        call_command('create_tenant', 'tenant')
        Tenant.objects.get(name='tenant').delete()