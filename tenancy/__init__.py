from __future__ import unicode_literals

from django.utils.version import get_version

VERSION = (0, 3, 0, 'alpha', 1)

__version__ = get_version(VERSION)

default_app_config = 'tenancy.apps.TenancyConfig'


def get_tenant_model():
    from django.core.exceptions import ImproperlyConfigured
    from .models import AbstractTenant
    from .utils import get_model
    from .settings import TENANT_MODEL

    app_label, object_name = TENANT_MODEL.split('.')
    model_name = object_name.lower()
    tenant_model = get_model(app_label, model_name)
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
