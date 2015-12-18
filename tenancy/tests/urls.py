from __future__ import unicode_literals

from django.conf.urls import url
from django.http import HttpResponse

from .views import raise_exception, tenant_name

urlpatterns = [
    url(r'^$',
        lambda request: HttpResponse(),
        name='default'),
    url(r'^global$',
        tenant_name,
        name='tenant'),
    url(r'^exception$',
        raise_exception,
        name='exception'),
]
