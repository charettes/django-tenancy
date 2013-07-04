from __future__ import unicode_literals

from django.conf.urls import patterns, url
from django.http import HttpResponse

from ..models import Tenant


urlpatterns = patterns('',
    url(r'^$',
        lambda request: HttpResponse(getattr(request, Tenant.ATTR_NAME).name),
        name='tenant_name'
    ),
)
