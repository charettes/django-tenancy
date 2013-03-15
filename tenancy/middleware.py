from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, DEFAULT_DB_ALIAS
from django.http import Http404

from . import get_tenant_model


class TenantHostMiddleware(object):
    def __init__(self):
        try:
            import django_hosts
        except ImportError:  #pragma: no cover
            raise ImproperlyConfigured(
                'You must install django-hosts in order to '
                'use `TenantHostMiddleware`.'
            )
        path = "%s.%s" % (self.__module__, self.__class__.__name__)
        for middleware in settings.MIDDLEWARE_CLASSES:
            if middleware == 'django_hosts.middleware.HostsMiddleware':
                break
            elif middleware == path:
                raise ImproperlyConfigured(
                    "Make sure that 'django_hosts.middleware.HostsMiddleware' "
                    "is placed before '%s' in your `MIDDLEWARE_CLASSES` "
                    "setting." % path
                )

    def process_request(self, request):
        if request.host.name == 'tenant':
            tenant_model = get_tenant_model()
            match = request.host.compiled_regex.match(request.get_host())
            lookups = match.groupdict()
            try:
                tenant = tenant_model._default_manager.get(**lookups)
            except tenant_model.DoesNotExist:
                raise Http404("No tenant found for specified lookups: %r" % lookups)
            request.tenant = tenant


class GlobalTenantMiddleware(object):
    """
    Middleware that assigns the request's tenant attribute to the default
    connection object. This unfortunate global state is required in order to
    allow things such as a tenant custom user with the required auth backend.
    """

    def get_global_state(self):
        return connections[DEFAULT_DB_ALIAS]

    def process_request(self, request):
        setattr(self.get_global_state(), 'tenant', getattr(request, 'tenant'))

    def process_response(self, request, response):
        self.process_exception(request, None)
        return response

    def process_exception(self, request, exception):
        delattr(self.get_global_state(), 'tenant')
