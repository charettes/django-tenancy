from __future__ import unicode_literals


__version__ = (0, 1, 1)


def get_tenant_model(seed_cache=True):
    from django.core.exceptions import ImproperlyConfigured
    from django.db.models import get_model
    from .models import AbstractTenant
    from .settings import TENANT_MODEL

    app_label, object_name = TENANT_MODEL.split('.')
    model_name = object_name.lower()
    tenant_model = get_model(
        app_label, model_name, seed_cache=seed_cache, only_installed=False
    )
    if tenant_model is None:
        raise ImproperlyConfigured(
            "TENANCY_TENANT_MODEL refers to model '%s.%s' that has not "
            "been installed" % (app_label, object_name)
        )
    elif not issubclass(tenant_model, AbstractTenant):
        raise ImproperlyConfigured(
            "TENANCY_TENANT_MODEL refers to models '%s.%s' which is not a "
            "subclass of 'tenancy.AbstractTenant'" % (app_label, object_name))
    return tenant_model
