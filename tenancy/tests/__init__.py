from __future__ import unicode_literals
from functools import wraps
import pickle
import sys

import django
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, models as django_models
from django.template.base import TemplateDoesNotExist
from django.test.testcases import TransactionTestCase
from django.test.utils import override_settings
from django.utils.functional import cached_property
from django.utils.unittest.case import skipIf, skipUnless

from .. import get_tenant_model
from ..auth.backends import CustomTenantUserBackend
from ..forms import (tenant_inlineformset_factory, tenant_modelform_factory,
    tenant_modelformset_factory)
from ..middleware import TenantHostMiddleware
from ..models import (db_schema_table, Tenant, TenantModel, TenantModelBase,
    TenantModelDescriptor)
from ..views import TenantObjectMixin
from ..utils import model_name_from_opts

from .client import TenantClient
from .forms import SpecificModelForm
from .models import (AbstractTenantModel, AbstractSpecificModelSubclass,
    M2MSpecific, NonTenantModel, RelatedSpecificModel, RelatedTenantModel,
    SpecificModel, SpecificModelProxy, SpecificModelProxySubclass,
    SpecificModelSubclass, SpecificModelSubclassProxy, TenantModelMixin)
from .views import (InvalidModelFormClass, InvalidModelMixin,
    MissingModelMixin, NonTenantModelFormClass, SpecificModelMixin,
    SpecificModelFormMixin, UnspecifiedFormClass)
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
    def test_simple_instancecheck(self):
        instance = self.tenant.specificmodels.create()
        self.assertIsInstance(instance, django_models.Model)
        self.assertIsInstance(instance, TenantModelMixin)
        self.assertIsInstance(instance, SpecificModel)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def test_concrete_inheritance_instancecheck(self):
        instance = self.tenant.specific_models_subclasses.create()
        self.assertIsInstance(instance, django_models.Model)
        self.assertIsInstance(instance, TenantModelMixin)
        self.assertIsInstance(instance, SpecificModel)
        self.assertIsInstance(instance, SpecificModelSubclass)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def test_proxy_inheritance_instancecheck(self):
        instance = self.tenant.specific_model_proxies.create()
        self.assertIsInstance(instance, django_models.Model)
        self.assertIsInstance(instance, TenantModelMixin)
        self.assertIsInstance(instance, SpecificModel)
        self.assertIsInstance(instance, SpecificModelProxy)
        self.assertNotIsInstance(instance, RelatedSpecificModel)
        self.assertNotIsInstance(instance, TenantModelBaseTest)

    def assertIsSubclass(self, cls, base):
        self.assertTrue(issubclass(cls, base))

    def assertIsNotSubclass(self, cls, base):
        self.assertFalse(issubclass(cls, base))

    def test_subclasscheck(self):
        self.assertIsSubclass(SpecificModel, TenantModelMixin)
        tenant_specific_model = self.tenant.specificmodels.model
        self.assertIsSubclass(tenant_specific_model, AbstractTenantModel)
        self.assertIsSubclass(tenant_specific_model, SpecificModel)
        self.assertIsNotSubclass(tenant_specific_model, RelatedSpecificModel)
        self.assertIsNotSubclass(tenant_specific_model, tuple)
        self.assertIsSubclass(tenant_specific_model, django_models.Model)

    def test_concrete_inheritance_subclasscheck(self):
        tenant_specific_model = self.tenant.specificmodels.model
        tenant_specific_model_subclass = self.tenant.specific_models_subclasses.model
        self.assertIsSubclass(tenant_specific_model_subclass, SpecificModel)
        self.assertIsSubclass(tenant_specific_model_subclass, tenant_specific_model)

    def test_proxy_inheritance_subclasscheck(self):
        tenant_specific_model = self.tenant.specificmodels.model
        tenant_specific_model_proxy = SpecificModelProxy.for_tenant(self.tenant)
        self.assertIsSubclass(tenant_specific_model_proxy, SpecificModel)
        self.assertIsSubclass(tenant_specific_model_proxy, tenant_specific_model)

    def assertPickleEqual(self, obj):
        pickled = pickle.dumps(obj)
        self.assertEqual(pickle.loads(pickled), obj)

    @skipIf(sys.version_info < (2, 7),
            "Model class can't be pickled on python < 2.7")
    def test_pickling(self):
        self.assertPickleEqual(SpecificModel)
        self.assertPickleEqual(self.tenant.specificmodels.model)
        self.assertPickleEqual(self.tenant.specificmodels.model.__bases__[0])
        self.assertPickleEqual(self.tenant.specific_models_subclasses.model)
        self.assertPickleEqual(self.tenant.specific_models_subclasses.model.__bases__[0])

    def test_tenant_specific_model_dynamic_subclassing(self):
        """
        Make sure tenant specific models can be dynamically subclassed.
        """
        model = self.tenant.specificmodels.model
        model_subclass = type(
            str("%sSubclass" % model.__name__),
            (model,),
            {'__module__': model.__module__}
        )
        self.assertEqual(model.tenant, model_subclass.tenant)


class TenantModelDescriptorTest(TenancyTestCase):
    def test_class_accessing(self):
        """
        Make sure the descriptor is available from the class.
        """
        self.assertIsInstance(Tenant.specificmodels, TenantModelDescriptor)

    def test_related_name(self):
        """
        Make sure the descriptor is correctly attached to the Tenant model
        when the related_name is specified or not.
        """
        self.assertTrue(issubclass(
            self.tenant.specificmodels.model, SpecificModel)
        )
        self.assertTrue(issubclass(
            self.tenant.related_specific_models.model, RelatedSpecificModel)
        )

    def test_content_type_created(self):
        """
        Make sure the content type associated with the returned model is
        always created.
        """
        opts = self.tenant.specificmodels.model._meta
        self.assertTrue(
            ContentType.objects.filter(
                app_label=opts.app_label,
                model=model_name_from_opts(opts)
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

    def test_db_table(self):
        """
        Make sure the `db_table` associated with tenant models is correctly
        prefixed based on the tenant and suffixed by the un-managed model's
        `db_table`.
        """
        self.assertEqual(
            self.tenant.specificmodels.model._meta.db_table,
            db_schema_table(self.tenant, SpecificModel._meta.db_table)
        )
        self.assertEqual(
            self.tenant.specific_models_subclasses.model._meta.db_table,
            db_schema_table(self.tenant, SpecificModelSubclass._meta.db_table)
        )

    def test_field_names(self):
        """
        Make sure tenant specific models' fields are the same as the one
        defined on the un-managed one.
        """
        models = (
            SpecificModel,
            SpecificModelSubclass,  # Test inheritance scenarios
            RelatedTenantModel,  # And models with m2m fields
        )
        for tenant in Tenant.objects.all():
            for model in models:
                opts = model._meta
                tenant_model = model.for_tenant(tenant)
                tenant_opts = tenant_model._meta
                for field in (opts.local_fields + opts.many_to_many):
                    tenant_field = tenant_opts.get_field(field.name)
                    self.assertEqual(tenant_field.__class__, field.__class__)

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

    def test_m2m(self):
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

    def test_m2m_with_through(self):
        for tenant in Tenant.objects.all():
            related = tenant.related_tenant_models.create()
            specific = tenant.specificmodels.create()
            tenant.m2m_specifics.create(
                related=related,
                specific=specific
            )
            self.assertEqual(related.m2m_through.get(), specific)
            self.assertEqual(specific.m2ms_through.get(), related)

    def test_m2m_to_non_tenant(self):
        """
        Make sure m2m between TenantModels work correctly.
        """
        for tenant in Tenant.objects.all():
            # Test object creation
            related = tenant.related_tenant_models.create()
            non_tenant = related.m2m_non_tenant.create()
            # Test reverse related manager
            reverse_descriptor_name = "tenant_%s_relatedtenantmodels" % tenant.name
            self.assertEqual(getattr(non_tenant, reverse_descriptor_name).get(), related)
            # Test reverse filtering
            self.assertEqual(NonTenantModel.objects.filter(
                **{reverse_descriptor_name:related}).get(), non_tenant)

    def test_not_managed_auto_intermediary_model(self):
        """
        Make sure that exposed un-managed models with m2m relations have their
        intermediary models also un-managed.
        """
        get_field = RelatedTenantModel._meta.get_field
        self.assertFalse(get_field('m2m').rel.through._meta.managed)
        self.assertFalse(get_field('m2m_to_undefined').rel.through._meta.managed)
        self.assertFalse(get_field('m2m_through').rel.through._meta.managed)
        self.assertFalse(get_field('m2m_recursive').rel.through._meta.managed)
        self.assertFalse(get_field('m2m_non_tenant').rel.through._meta.managed)

    def test_invalid_foreign_key_related_name(self):
        # Ensure `related_name` with no %(tenant)s format placeholder also
        # raises an improperly configured error.
        with self.assertRaisesMessage(ImproperlyConfigured,
            "Since `InvalidRelatedName.fk` is originating from an instance "
            "of `TenantModelBase` and not pointing to one "
            "its `related_name` option must ends with a "
            "'+' or contain the '%(class)s' format "
            "placeholder."):
            class InvalidRelatedName(TenantModel):
                fk = django_models.ForeignKey(NonTenantModel, related_name='no-tenant')

    def test_invalid_m2m_through(self):
        with self.assertRaisesMessage(ImproperlyConfigured,
            "Since `InvalidThrough.m2m` is originating from an instance of "
            "`TenantModelBase` its `through` option must also be pointing "
            "to one."):
            class InvalidThrough(TenantModel):
                m2m = django_models.ManyToManyField(NonTenantModel,
                                                    through='InvalidIntermediary')
            class InvalidIntermediary(django_models.Model):
                pass

    def test_non_tenant_related_descriptor(self):
        """
        Make sure related descriptor are correctly attached to non-tenant
        models and removed on tenant deletion.
        """
        for tenant in Tenant.objects.all():
            attr = "tenant_%s_specificmodels" % tenant.name
            self.assertTrue(hasattr(NonTenantModel, attr))
            tenant.delete()
            self.assertFalse(hasattr(NonTenantModel, attr))

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
                 django_models.signals.pre_init,
                 django_models.signals.post_init,
                 django_models.signals.pre_save,
                 django_models.signals.post_save,
                 django_models.signals.pre_delete,
                 django_models.signals.post_delete
                 ]
            )


class NonTenantModelTest(TransactionTestCase):
    def test_fk_to_tenant(self):
        """
        Non-tenant models shouldn't be allowed to have a ForeignKey pointing
        to an instance of `TenantModelBase`.
        """
        with self.assertRaisesMessage(ImproperlyConfigured,
            "`NonTenantFkToTenant.fk`'s `to` option` can't point to an "
            "instance of `TenantModelBase` since it's not one itself."):
            class NonTenantFkToTenant(django_models.Model):
                fk = django_models.ForeignKey('UndeclaredSpecificModel')
            class UndeclaredSpecificModel(TenantModel):
                pass

    def test_m2m_to_tenant(self):
        """
        Non-tenant models shouldn't be allowed to have ManyToManyField pointing
        to an instance of `TenantModelBase`.
        """
        with self.assertRaisesMessage(ImproperlyConfigured,
            "`NonTenantM2MToTenant.m2m`'s `to` option` can't point to an "
            "instance of `TenantModelBase` since it's not one itself."):
            class NonTenantM2MToTenant(django_models.Model):
                m2m = django_models.ManyToManyField(SpecificModel)


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


@override_settings(
    ROOT_URLCONF='tenancy.tests.urls',
    MIDDLEWARE_CLASSES=(
        'tenancy.middleware.GlobalTenantMiddleware',
    )
)
class GlobalTenantMiddlewareTest(TenancyTestCase):
    def setUp(self):
        super(GlobalTenantMiddlewareTest, self).setUp()
        self.client = TenantClient(self.tenant)

    def test_process_response(self):
        response = self.client.get('/tenant')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.tenant.name)
        self.assertRaises(AttributeError, getattr, connection, 'tenant')

    def test_process_exception(self):
        with self.assertRaisesMessage(Exception, self.tenant.name):
            self.client.get('/exception')
        self.assertRaises(AttributeError, getattr, connection, 'tenant')


try:
    import django_hosts
except ImportError:
    django_hosts_installed = False
else:
    django_hosts_installed = True


def django_hosts_installed_setup(func):
    func = override_settings(
        ROOT_URLCONF='tenancy.tests.urls',
        DEFAULT_HOST='default',
        ROOT_HOSTCONF='tenancy.tests.hosts',
        MIDDLEWARE_CLASSES=(
            'django_hosts.middleware.HostsMiddleware',
            'tenancy.middleware.TenantHostMiddleware'
        )
    )(func)
    return skipUnless(
        django_hosts_installed,
        'django-hosts is not installed.'
    )(func)


class TenantHostMiddlewareTest(TenancyTestCase):
    @classmethod
    def tenant_client(cls, tenant):
        domain = "%s.testserver" % tenant.name
        return cls.client_class(SERVER_NAME=domain)

    @skipIf(django_hosts_installed, 'django-hosts is installed.')
    def test_not_installed(self):
        self.assertRaisesMessage(
            ImproperlyConfigured,
            'You must install django-hosts in order to use '
            '`TenantHostMiddleware`.',
            TenantHostMiddleware
        )

    @skipUnless(django_hosts_installed, 'django-hosts is not installed.')
    @override_settings(
        MIDDLEWARE_CLASSES=(
            'tenancy.middleware.TenantHostMiddleware',
            'django_hosts.middleware.HostsMiddleware'
        )
    )
    def test_wrong_order(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "Make sure that 'django_hosts.middleware.HostsMiddleware' is "
            "placed before 'tenancy.middleware.TenantHostMiddleware' in your "
            "`MIDDLEWARE_CLASSES` setting.",
            TenantHostMiddleware
        )

    @django_hosts_installed_setup
    def test_tenant_not_found(self):
        tenant = Tenant(name='inexistent')
        client = self.tenant_client(tenant)
        # TODO: Remove when support for Django < 1.5 is dropped
        try:
            response = client.get('/')
        except TemplateDoesNotExist as e:
            self.assertEqual(str(e), '404.html')
        else:
            self.assertEqual(response.status_code, 404)

    @django_hosts_installed_setup
    def test_tenant_found(self):
        client = self.tenant_client(self.tenant)
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.tenant.name)


try:
    from django.contrib.auth import get_user_model
except ImportError:
    has_custom_user_support = False
else:
    has_custom_user_support = True


def custom_user_setup(func):
    @wraps(func)
    def wrapped(self, *args, **kwargs):
        with self.tenant.as_global():
            func(self, *args, **kwargs)
    return skipUnless(
        has_custom_user_support,
        'No custom user support.'
    )(override_settings(AUTH_USER_MODEL='tenancy.TenantUser')(wrapped))


class CustomTenantUserBackendTest(TenancyTestCase):
    @skipIf(has_custom_user_support, 'Has custom user support.')
    def test_no_custom_user_support(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend requires custom user support a "
            "feature introduced in django 1.5",
            CustomTenantUserBackend
        )

    @skipUnless(has_custom_user_support, 'No custom user support.')
    @override_settings(AUTH_USER_MODEL='auth.User')
    def test_custom_user_not_tenant(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend can only be used with a custom "
            "tenant user model.",
            CustomTenantUserBackend
        )

    @skipUnless(has_custom_user_support, 'No custom user support.')
    @override_settings(AUTH_USER_MODEL='tenancy.TenantUser')
    def test_missing_connection_tenant(self):
        self.assertRaisesMessage(ImproperlyConfigured,
            "The `tenancy.auth.backends.CustomTenantUserBackend` "
            "authentification backend requires that a `tenant` attribute "
            "be set on the default connection to work properly. The "
            "`tenancy.middleware.GlobalTenantMiddlewareTest` does "
            "just that.",
            CustomTenantUserBackend
        )

    @custom_user_setup
    def test_authenticate(self):
        backend = CustomTenantUserBackend()
        user = self.tenant.users.model(email='p.roy@habs.ca')
        user.set_password('numero 33')
        user.save()
        self.assertIsNone(backend.authenticate(email='nobody@nowhere.ca'))
        self.assertIsNone(backend.authenticate('p.roy@habs.ca'))
        self.assertTrue(backend.authenticate('p.roy@habs.ca', 'numero 33'))

    @custom_user_setup
    def test_get_user(self):
        backend = CustomTenantUserBackend()
        user = self.tenant.users.create(email='latitude-e4200@dell.com')
        self.assertIsNone(backend.get_user(user.pk+1))
        self.assertEqual(user, backend.get_user(user.pk))


try:
    from mutant.contrib.boolean.models import NullBooleanFieldDefinition
except ImportError:
    mutant_installed = False
else:
    mutant_installed = True


@skipUnless(mutant_installed, 'django-mutant is not installed.')
@skipIf(sys.version_info < (2, 7), "Model class can't be pickled on python < 2.7")
class MutableTenantModelTest(TenancyTestCase):
    def test_field_creation(self):
        from .models import MutableTenantModel, MutableTenantModelSubclass
        model_class = MutableTenantModel.for_tenant(self.tenant)
        model_def = model_class.definition()
        NullBooleanFieldDefinition.objects.create(
            model_def=model_def,
            name='is_cool'
        )
        tenant_mutable_models = self.tenant.mutable_models
        tenant_mutable_models.create(field='test', is_cool=False)
        self.assertEqual(1, tenant_mutable_models.filter(is_cool=False).count())

    def test_subclassing(self):
        from .models import MutableTenantModel, MutableTenantModelSubclass
        model_class = MutableTenantModelSubclass.for_tenant(self.tenant)
        specific_model = self.tenant.specificmodels.create()
        model_class.objects.create(field='test', non_mutable_fk=specific_model)
        # Add a field to the parent class
        NullBooleanFieldDefinition.objects.create_with_default(False,
            model_def=MutableTenantModel.for_tenant(self.tenant).definition(),
            name='is_cool',
        )
        self.assertEqual(1,
            model_class.objects.filter(field='test', is_cool=False).count()
        )
