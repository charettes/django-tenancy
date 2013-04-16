from __future__ import unicode_literals

from django.conf.urls import patterns, url
from django.db import connection
from django.http import HttpResponse

from .views import raise_exception


urlpatterns = patterns('',
    url(r'^$',
        lambda request: HttpResponse(),
        name='default'
    ),
    url(r'^global$',
        lambda request: HttpResponse(
            connection.tenant.name if connection.tenant else ''
        ),
        name='tenant'
    ),
    url(r'^exception$',
        raise_exception,
        name='exception'
    )
)
