from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured
from django.forms.models import (inlineformset_factory, ModelForm,
    modelform_factory, modelformset_factory)

from .models import TenantModelBase


def _get_tenant_model(tenant, model):
    if not isinstance(model, TenantModelBase):
        raise ImproperlyConfigured(
            "%s must be an instance of TenantModelBase" % model.__name__
        )
    return model.for_tenant(tenant)


def tenant_modelform_factory(tenant, model, *args, **kwargs):
    return modelform_factory(
        model=_get_tenant_model(tenant, model),*args, **kwargs
    )


def tenant_modelformset_factory(tenant, model, *args, **kwargs):
    return modelformset_factory(
        model=_get_tenant_model(tenant, model), *args, **kwargs
    )


def tenant_inlineformset_factory(tenant, parent_model, model, form=ModelForm,
                                 *args, **kwargs):
    try:
        parent_model = _get_tenant_model(tenant, parent_model)
    except ImproperlyConfigured:
        # Allow parent model to be non-tenant model
        pass
    tenant_model = _get_tenant_model(tenant, model)
    if form is not ModelForm:
        form = modelform_factory(tenant_model, form=form)
    return inlineformset_factory(
        parent_model=parent_model, model=tenant_model, form=form, *args,**kwargs
    )
