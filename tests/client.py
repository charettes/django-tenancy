from __future__ import unicode_literals

import weakref

from django.test.client import Client, ClientHandler


class TenantClientHandler(ClientHandler):
    def __init__(self, tenant, *args, **kwargs):
        self.tenant = weakref.ref(tenant)
        super(TenantClientHandler, self).__init__(*args, **kwargs)

    def get_response(self, request):
        tenant = self.tenant()
        setattr(request, tenant.ATTR_NAME, tenant)
        return super(TenantClientHandler, self).get_response(request)


class TenantClient(Client):
    def __init__(self, tenant, enforce_csrf_checks=False, **defaults):
        super(Client, self).__init__(**defaults)
        self.handler = TenantClientHandler(tenant, enforce_csrf_checks)
        self.exc_info = None
