from __future__ import unicode_literals

from django_hosts import host, patterns

from ..settings import HOST_NAME


host_patterns = patterns('',
    host(r'(?P<name>[\w-]+)', 'tenancy.tests.tenant_urls', name=HOST_NAME),
    host(r'', 'tenancy.tests.urls', name='default'),
)
