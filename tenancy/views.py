from __future__ import unicode_literals

import warnings

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Manager
from django.db.models.query import QuerySet
from django.forms.models import (
    BaseInlineFormSet, BaseModelFormSet, ModelForm, modelform_factory,
)
from django.utils.functional import cached_property
from django.views.generic.edit import ModelFormMixin

from . import get_tenant_model
from .forms import (
    tenant_inlineformset_factory, tenant_modelform_factory,
    tenant_modelformset_factory,
)
from .models import TenantModelBase, TenantSpecificModel


class TenantMixin(object):
    """
    View mixin that retrieve the current tenant from the request. This could
    have been set from a middleware base on a domain name for example.
    """
    tenant_attr_name = get_tenant_model().ATTR_NAME

    def get_tenant(self):
        return getattr(self.request, self.tenant_attr_name)

setattr(
    TenantMixin, get_tenant_model().ATTR_NAME,
    cached_property(lambda self: self.get_tenant())
)


class TenantObjectMixin(TenantMixin):
    """
    View mixin that returns the correct queryset for the specified model based
    on the retrieved tenant.
    """
    model = None
    context_object_name = None

    def get_model(self):
        if self.model:
            if not isinstance(self.model, TenantModelBase):
                msg = "%s.model is not an instance of TenantModelBase."
                raise ImproperlyConfigured(msg % self.__class__.__name__)
            return self.model
        raise ImproperlyConfigured(
            "%s is missing a model." % self.__class__.__name__
        )

    def get_tenant_model(self):
        tenant = self.get_tenant()
        return tenant.models[self.get_model()]

    def get_queryset(self):
        return self.get_tenant_model()._default_manager.all()

    def get_template_names(self):
        try:
            names = super(TenantObjectMixin, self).get_template_names()
        except (AttributeError, ImproperlyConfigured):
            names = []

        model = self.get_model()
        names.append("%s/%s%s.html" % (
            model._meta.app_label,
            model._meta.model_name,
            getattr(self, 'template_name_suffix', ''),
        ))

        return names

    def get_context_object_name(self, obj):
        if self.context_object_name:
            return self.context_object_name
        elif (isinstance(obj, (Manager, QuerySet)) and
              issubclass(obj.model, TenantSpecificModel)):
            return "%s_list" % obj.model._for_tenant_model._meta.model_name
        elif isinstance(obj, TenantSpecificModel):
            return obj._for_tenant_model._meta.model_name


class TenantModelFormMixin(TenantObjectMixin, ModelFormMixin):
    def get_form_class(self):
        """
        Provide a model form class based on tenant specific model.
        """
        form_class = self.form_class
        fields = self.fields
        if form_class:
            if issubclass(form_class, ModelForm):
                model = form_class._meta.model
                factory = tenant_modelform_factory
            elif issubclass(form_class, BaseModelFormSet):
                model = form_class.model
                if issubclass(form_class, BaseInlineFormSet):
                    factory = tenant_inlineformset_factory
                else:
                    factory = tenant_modelformset_factory
            else:
                raise ImproperlyConfigured(
                    "%s.form_class must be a subclass of `ModelForm` or "
                    "`BaseModelFormSet`." % self.__class__.__name__
                )
            if model:
                if not isinstance(model, TenantModelBase):
                    raise ImproperlyConfigured(
                        "%s.form_class' model is not an instance of "
                        "TenantModelBase." % self.__class__.__name__
                    )
                return factory(self.get_tenant(), form_class)
        else:
            form_class = ModelForm
            if fields is None:
                warnings.warn(
                    "Using TenantModelFormMixin (base class of %s) without "
                    "the 'fields' attribute is deprecated." % self.__class__.__name__,
                    DeprecationWarning,
                )
        return modelform_factory(
            self.get_tenant_model(), form_class, fields=fields
        )


class TenantWizardMixin(TenantMixin):
    def get_form(self, step=None, data=None, files=None):
        if step is None:
            step = self.steps.current
        kwargs = self.get_form_kwargs(step)
        form_class = self.form_list[step]
        if (issubclass(form_class, ModelForm) and
                isinstance(form_class._meta.model, TenantModelBase)):
            kwargs.setdefault('instance', self.get_form_instance(step))
            form_class = tenant_modelform_factory(self.get_tenant(), form_class)
        elif (issubclass(form_class, BaseModelFormSet) and
              isinstance(form_class.model, TenantModelBase)):
            kwargs.setdefault('queryset', self.get_form_instance(step))
            tenant = self.get_tenant()
            if isinstance(form_class, BaseInlineFormSet):
                form_class = tenant_inlineformset_factory(tenant, form_class)
            else:
                form_class = tenant_modelformset_factory(tenant, form_class)
        else:
            return super(TenantWizardMixin, self).get_form(step, data, files)
        kwargs.update({
            'data': data,
            'files': files,
            'prefix': self.get_form_prefix(step, form_class),
            'initial': self.get_form_initial(step),
        })
        return form_class(**kwargs)
