SECRET_KEY = 'not-anymore'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'tenancy',
    'tests',
]

ROOT_URLCONF = 'tests.urls'

SILENCED_SYSTEM_CHECKS = ['1_7.W001']

try:
    import mutant  # NOQA
except ImportError:
    pass
else:
    INSTALLED_APPS.append('mutant')
