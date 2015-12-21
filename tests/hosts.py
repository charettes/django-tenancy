from __future__ import unicode_literals

from django_hosts import host

from tenancy.settings import HOST_NAME

host_patterns = [
    host(r'(?P<name>[\w-]+)', 'tests.tenant_urls', name=HOST_NAME),
    host(r'', 'tests.urls', name='default'),
]
