from __future__ import unicode_literals

from django.conf.urls import patterns, url
from django.http import HttpResponse


urlpatterns = patterns('',
    url(r'^$',
        lambda request: HttpResponse(request.tenant.name),
        name='tenant_name'
    ),
)
