SECRET_KEY = 'not-anymore'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'tenancy',
]

ROOT_URLCONF = 'tenancy.tests.urls'

try:
    import mutant
except ImportError:
    pass
else:
    INSTALLED_APPS.append('mutant')
