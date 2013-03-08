from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.forms.models import ModelForm, modelform_factory
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import ModelFormMixin

from .models import TenantModelBase


class TenantMixin(object):
    """
    View mixin that retrieve the current tenant from the request. This could
    have been set from a middleware base on a domain name for example.
    """

    def get_tenant(self):
        return self.request.tenant


class SingleTenantObjectMixin(TenantMixin, SingleObjectMixin):
    """
    View mixin that returns the correct queryset for the specified model based
    on the retrieved tenant.
    """

    def get_queryset(self):
        if self.model:
            if not isinstance(self.model, TenantModelBase):
                msg = "%s.model is not an instance of TenantModelBase."
                raise ImproperlyConfigured(msg % self.__class__.__name__)
            tenant = self.get_tenant()
            related_name = self.model._tenant_meta.related_name
            return getattr(tenant, related_name).all()
        raise ImproperlyConfigured("%s is missing a model." %
                                   self.__class__.__name__)


class TenantModelFormMixin(SingleTenantObjectMixin, ModelFormMixin):
    def get_form_class(self):
        """
        Provide a model form class based on tenant specific model.

        If a `form_class` attribute is specified it makes sure it's associated
        model is coherent with the one specified on this class.
        """
        form_class = self.form_class
        model = self.get_queryset().model
        if form_class:
            form_class_model = form_class._meta.model
            if form_class_model:
                if isinstance(form_class_model, TenantModelBase):
                    if not issubclass(model, form_class_model):
                        msg = "%s's model: %s, is not a subclass of it's `form_class` model: %s."
                        raise ImproperlyConfigured(
                            msg % (
                                self.__class__.__name__,
                                model.__name__,
                                form_class_model.__name__
                            )
                        )
                else:
                    msg = "%s.form_class' model is not an instance of TenantModelBase."
                    raise ImproperlyConfigured(msg % self.__class__.__name__)
        else:
            form_class = ModelForm
        return modelform_factory(model, form_class)
