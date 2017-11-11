from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, connections
from django.http import Http404

from . import get_tenant_model
from .settings import HOST_NAME

try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    MiddlewareMixin = object


class TenantHostMiddleware(MiddlewareMixin):
    def __init__(self, *args, **kwargs):
        super(TenantHostMiddleware, self).__init__(*args, **kwargs)
        try:
            import django_hosts  # NOQA
        except ImportError:
            raise ImproperlyConfigured(
                'You must install django-hosts in order to use `TenantHostMiddleware`.'
            )
        django_hosts_middleware = 'django_hosts.middleware.HostsRequestMiddleware'
        path = "%s.%s" % (self.__module__, self.__class__.__name__)
        for setting in ('MIDDLEWARE', 'MIDDLEWARE_CLASSES'):
            middlewares = getattr(settings, setting, None)
            if middlewares is None:
                continue
            for middleware in middlewares:
                if middleware == django_hosts_middleware:
                    break
                elif middleware == path:
                    raise ImproperlyConfigured(
                        "Make sure '%s' appears before '%s' in your `%s` setting." % (
                            django_hosts_middleware, path, setting,
                        )
                    )
            break
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


class GlobalTenantMiddleware(MiddlewareMixin):
    """
    Middleware that assigns the request's tenant attribute to the default
    connection object. This unfortunate global state is required in order to
    allow things such as a tenant custom user with the required auth backend.
    """

    def __init__(self, *args, **kwargs):
        super(GlobalTenantMiddleware, self).__init__(*args, **kwargs)
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
