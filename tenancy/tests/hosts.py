from __future__ import unicode_literals

from django_hosts import host, patterns


host_patterns = patterns('',
    host(r'(?P<name>[\w-]+)', 'tenancy.tests.tenant_urls', name='tenant'),
    host(r'', 'tenancy.tests.urls', name='default'),
)
