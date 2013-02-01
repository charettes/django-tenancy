SECRET_KEY = 'not-anymore'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'tenancy',
]

try:
    import django_coverage
except ImportError:
    pass
else:
    INSTALLED_APPS.append('django_coverage')