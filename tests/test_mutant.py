from __future__ import unicode_literals

from unittest import skipUnless

from tenancy.compat import get_remote_field_model

from .utils import TenancyTestCase

try:
    from mutant.models import BaseDefinition, ModelDefinition
    from mutant.contrib.boolean.models import NullBooleanFieldDefinition
    from .models import MutableModel, MutableModelSubclass, NonMutableModel
except ImportError:
    mutant_installed = False
else:
    mutant_installed = True


@skipUnless(mutant_installed, 'django-mutant is not installed.')
class MutableTenantModelTest(TenancyTestCase):
    def test_field_creation(self):
        model_class = MutableModel.for_tenant(self.tenant)
        model_def = model_class.definition()
        NullBooleanFieldDefinition.objects.create(
            model_def=model_def,
            name='is_cool'
        )
        tenant_mutable_models = self.tenant.mutable_models
        tenant_mutable_models.create(field='test', is_cool=False)
        self.assertEqual(1, tenant_mutable_models.filter(is_cool=False).count())

    def test_subclassing(self):
        model_class = MutableModelSubclass.for_tenant(self.tenant)
        self.assertEqual(
            get_remote_field_model(model_class._meta.get_field('non_mutable_fk')),
            self.tenant.specificmodels.model
        )
        specific_model = self.tenant.specificmodels.create()
        mutable = model_class.objects.create(
            field=True, non_mutable_fk=specific_model
        )
        # Make sure the reverse descriptor is accessible before mutation
        self.assertEqual(specific_model.mutables.get(), mutable)
        # Add a field to the parent class
        NullBooleanFieldDefinition.objects.create(
            model_def=MutableModel.for_tenant(self.tenant).definition(),
            name='is_cool',
        )
        # Make sure the reverse descriptor is accessible after mutation
        self.assertEqual(specific_model.mutables.get(), mutable)
        self.assertEqual(
            1,
            model_class.objects.filter(
                field=True, is_cool=None, non_mutable_fk=specific_model
            ).count()
        )

    def test_ordering(self):
        """
        Ordering is not inherited from an abstract base class thus
        OrderingFieldDefinition must be created in order to maintain the
        specified ordering.
        """
        model_class = MutableModel.for_tenant(self.tenant)
        first = model_class.objects.create(field=True)
        second = model_class.objects.create(field=False)
        self.assertQuerysetEqual(
            model_class.objects.values_list('id', flat=True),
            sorted([second.id, first.id], reverse=True),
            int
        )

    def test_mutable_to_non_mutable_fk(self):
        """
        Make sure non mutable models reference mutable ones through a proxy.
        """
        mutable_model_class = MutableModel.for_tenant(self.tenant)
        mutable = mutable_model_class.objects.create(field=True)
        # Make sure the reverse descriptor is accessible before mutation
        self.assertFalse(mutable.non_mutables.exists())
        # Alter the model definition
        NullBooleanFieldDefinition.objects.create_with_default(
            False,
            model_def=mutable_model_class.definition(),
            name='is_cool',
        )
        mutable = mutable_model_class.objects.create(field=True)
        non_mutable_model_class = NonMutableModel.for_tenant(self.tenant)
        non_mutable = non_mutable_model_class.objects.create(mutable_fk=mutable)
        # Make sure the reverse descriptor is accessible after mutation
        self.assertEqual(mutable.non_mutables.get(), non_mutable)

    def test_cached_model_class(self):
        """
        Make sure mutable model class is also retrieved from app cache when
        possible.
        """
        model_class = MutableModel.for_tenant(self.tenant)
        with self.assertNumQueries(0):
            self.assertEqual(model_class, MutableModel.for_tenant(self.tenant))

    def test_dynamic_subclassing(self):
        """
        Tenant specific mutable models should be dynamically subclassable.
        """
        # Create the model definition.
        model_def = ModelDefinition.objects.create(
            bases=(BaseDefinition(base=MutableModel.for_tenant(self.tenant)),),
            app_label='tests',
            object_name='DynamicMutableSubclass',
        )
        # Alter the model definition.
        NullBooleanFieldDefinition.objects.create_with_default(
            False,
            model_def=model_def,
            name='is_cool',
        )
        # Delete the model definition.
        model_def.delete()
