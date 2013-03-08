from __future__ import unicode_literals

from django.conf.urls import patterns, url
from django.http import HttpResponse


urlpatterns = patterns('',
    url(r'^$',
        lambda request: HttpResponse(),
        name='default'
    ),
)
