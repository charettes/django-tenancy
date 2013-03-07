from __future__ import unicode_literals

from ..models import Tenant


class TenantMiddleware(object):
    def process_request(self, request):
        request.tenant = Tenant.objects.get(name='tenant')