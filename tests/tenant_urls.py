from __future__ import unicode_literals

from django.conf.urls import url
from django.http import HttpResponse

from tenancy.models import Tenant

urlpatterns = [
    url(r'^$',
        lambda request: HttpResponse(getattr(request, Tenant.ATTR_NAME).name),
        name='tenant_name'),
]
