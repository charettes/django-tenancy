from __future__ import  unicode_literals

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.test.testcases import TransactionTestCase

from .models import Tenant, TenantModel, TenantModelBase


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


class MultiTenantTest(BaseTenantTestCase):
    def test_isolation(self):
        """
        Make sure instances created in a tenant specific databases are shared
        between tenants.
        """
        self.tenant.related_specific_models.create()
        self.assertEqual(self.other_tenant.related_specific_models.count(), 0)
        self.other_tenant.related_specific_models.create()
        self.assertEqual(self.tenant.related_specific_models.count(), 1)


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


class TenantModelSubclassingTest(BaseTenantTestCase):
    def test_parents_tenant(self):
        """
        Make sure tenant model subclasses share the same tenant.
        """
        for tenant in Tenant.objects.all():
            parents = tenant.specific_models_subclasses.model._meta.parents
            for parent in parents:
                if isinstance(parent, TenantModelBase):
                    self.assertEqual(parent.tenant, tenant)