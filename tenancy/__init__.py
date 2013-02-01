from __future__ import unicode_literals

from django.core.exceptions import ImproperlyConfigured


__version__ = (0, 0, 1)


def get_tenant_model():
    from .settings import TENANT_MODEL
    from django.db.models import get_model

    try:
        app_label, model_name = TENANT_MODEL.split('.')
    except ValueError:
        raise ImproperlyConfigured("TENANCY_TENANT_MODEL must be of the form 'app_label.model_name'")
    tenant_model = get_model(app_label, model_name)
    if tenant_model is None:
        raise ImproperlyConfigured("TENANCY_TENANT_MODEL refers to model '%s' that has not been installed" % TENANT_MODEL)
    return tenant_model