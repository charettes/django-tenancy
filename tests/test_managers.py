from __future__ import unicode_literals

from tenancy.models import Tenant

from .models import (
    SpecificModel, SpecificModelProxy, SpecificModelSubclass,
    SpecificModelSubclassProxy,
)
from .utils import TenancyTestCase


class TenantManagerTest(TenancyTestCase):
    def test_cache_on_init(self):
        # They were cached on `setUp`.
        self.assertEqual(
            id(self.tenant),
            id(Tenant.objects.get_by_natural_key(
                *self.tenant.natural_key()
            ))
        )
        self.assertEqual(
            id(self.other_tenant),
            id(Tenant.objects.get_by_natural_key(
                *self.other_tenant.natural_key()
            ))
        )

        Tenant.objects.clear_cache()
        for tenant in Tenant.objects.all():
            self.assertEqual(
                id(tenant),
                id(Tenant.objects._get_from_cache(*tenant.natural_key()))
            )

    def test_clear_cache(self):
        # They were cached on `setUp`.
        Tenant.objects.clear_cache()

        with self.assertRaises(KeyError):
            Tenant.objects._get_from_cache(*self.tenant.natural_key())
        with self.assertRaises(KeyError):
            Tenant.objects._get_from_cache(*self.other_tenant.natural_key())


class TenantModelManagerDescriptorTest(TenancyTestCase):
    def test_error_on_access(self):
        """
        Make sure managers can't be accessed from non-tenant-specific models.
        """
        # Concrete default manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModelSubclass is tenant "
            "specific"
        ):
            getattr(SpecificModelSubclass, 'objects')

        # Concrete default overridden manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModel is tenant specific"
        ):
            getattr(SpecificModel, 'objects')

        # Concrete custom manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModel is tenant specific"
        ):
            getattr(SpecificModel, 'custom_objects')

        # Proxy default manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModelSubclassProxy is tenant "
            "specific"
        ):
            getattr(SpecificModelSubclassProxy, 'objects')

        # Proxy default overridden manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModelProxy is tenant specific"
        ):
            getattr(SpecificModelProxy, 'objects')

        # Proxy custom manager
        with self.assertRaisesMessage(
            AttributeError,
            "Manager isn't available; SpecificModelProxy is tenant specific"
        ):
            getattr(SpecificModelProxy, 'proxied_objects')

    def test_allowed_access(self):
        """
        Make sure managers can be accessed from tenant specific models.
        """
        # Concrete default manager
        try:
            model = SpecificModelSubclass.for_tenant(self.tenant)
            getattr(model, 'objects')
        except AttributeError:
            self.fail(
                'Default manager should be accessible for concrete tenant '
                'specific model.'
            )

        # Concrete default overridden manager
        try:
            model = SpecificModel.for_tenant(self.tenant)
            getattr(model, 'objects')
        except AttributeError:
            self.fail(
                'Overridden default manager should be accessible for concrete '
                'tenant specific model.'
            )

        # Concrete custom manager
        try:
            model = SpecificModel.for_tenant(self.tenant)
            getattr(model, 'custom_objects')
        except AttributeError:
            self.fail(
                'Custom manager should be accessible for concrete '
                'tenant specific model.'
            )

        # Proxy default manager
        try:
            model = SpecificModelSubclassProxy.for_tenant(self.tenant)
            getattr(model, 'objects')
        except AttributeError:
            self.fail(
                'Proxy default manager should be accessible for concrete '
                'tenant specific models.'
            )

        # Proxy default overridden manager
        try:
            model = SpecificModelProxy.for_tenant(self.tenant)
            getattr(model, 'objects')
        except AttributeError:
            self.fail(
                'Proxy overridden default manager should be accessible for '
                'concrete tenant specific models.'
            )

        # Proxy custom manager
        try:
            model = SpecificModelProxy.for_tenant(self.tenant)
            getattr(model, 'proxied_objects')
        except AttributeError:
            self.fail(
                'Proxy custom manager should be accessible for '
                'concrete tenant specific models.'
            )
