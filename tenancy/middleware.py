from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, connections
from django.http import Http404

from . import get_tenant_model
from .settings import HOST_NAME


class TenantHostMiddleware(object):
    def __init__(self):
        try:
            import django_hosts  # NOQA
        except ImportError:
            raise ImproperlyConfigured(
                'You must install django-hosts in order to '
                'use `TenantHostMiddleware`.'
            )
        path = "%s.%s" % (self.__module__, self.__class__.__name__)
        for middleware in settings.MIDDLEWARE_CLASSES:
            if middleware == 'django_hosts.middleware.HostsRequestMiddleware':
                break
            elif middleware == path:
                raise ImproperlyConfigured(
                    "Make sure that 'django_hosts.middleware.HostsRequestMiddleware' "
                    "is placed before '%s' in your `MIDDLEWARE_CLASSES` "
                    "setting." % path
                )
        self.tenant_model = get_tenant_model()
        self.attr_name = self.tenant_model.ATTR_NAME

    def process_request(self, request):
        if request.host.name == HOST_NAME:
            match = request.host.compiled_regex.match(request.get_host())
            lookups = match.groupdict()
            tenant_model = self.tenant_model
            try:
                tenant = tenant_model._default_manager.get(**lookups)
            except tenant_model.DoesNotExist:
                raise Http404(
                    "No tenant found for specified lookups: %r" % lookups
                )
            setattr(request, self.attr_name, tenant)


class GlobalTenantMiddleware(object):
    """
    Middleware that assigns the request's tenant attribute to the default
    connection object. This unfortunate global state is required in order to
    allow things such as a tenant custom user with the required auth backend.
    """

    def __init__(self):
        self.attr_name = get_tenant_model().ATTR_NAME

    def get_global_state(self):
        return connections[DEFAULT_DB_ALIAS]

    def pollute_global_state(self, tenant):
        setattr(self.get_global_state(), self.attr_name, tenant)

    def clean_global_state(self):
        global_state = self.get_global_state()
        if hasattr(global_state, self.attr_name):
            delattr(global_state, self.attr_name)

    def process_request(self, request):
        self.pollute_global_state(
            getattr(request, self.attr_name, None)
        )

    def process_response(self, request, response):
        self.clean_global_state()
        return response

    def process_exception(self, request, exception):
        self.clean_global_state()
