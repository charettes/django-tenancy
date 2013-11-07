from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured

from .models import TenantModelBase


def _get_tenant_model(tenant, model):
    if not isinstance(model, TenantModelBase):
        raise ImproperlyConfigured(
            "%s must be an instance of TenantModelBase" % model.__name__
        )
    return tenant.models[model]


def tenant_modelform_factory(tenant, form):
    tenant_model = _get_tenant_model(tenant, form._meta.model)

    name = str("%s_%s" % (form.__name__, tenant.model_name_prefix))

    attrs = {'model': tenant_model}
    parent = (object,)
    if hasattr(form, 'Meta'):
        parent = (form.Meta, object)
    Meta = type(str('Meta'), parent, attrs)

    return type(name, (form,), {'Meta': Meta})


def tenant_modelformset_factory(tenant, formset):
    tenant_model = _get_tenant_model(tenant, formset.model)
    tenant_modelform = tenant_modelform_factory(tenant, formset.form)

    name = str("%s_%s" % (formset.__name__, tenant.model_name_prefix))
    attrs = {'model': tenant_model, 'form': tenant_modelform}

    return type(name, (formset,), attrs)


def tenant_inlineformset_factory(tenant, formset):
    tenant_modelformset = tenant_modelformset_factory(tenant, formset)
    fk = tenant_modelformset.model._meta.get_field(formset.fk.name)
    tenant_modelformset.fk = fk
    return tenant_modelformset
