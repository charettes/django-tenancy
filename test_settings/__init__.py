SECRET_KEY = 'not-anymore'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'tenancy',
]

try:
    import django_coverage
except ImportError:
    pass
else:
    INSTALLED_APPS.append('django_coverage')
    COVERAGE_MODULE_EXCLUDES = [
        'tests$',
        'settings$',
        'django'
    ]

try:
    import mutant
except ImportError:
    pass
else:
    INSTALLED_APPS.append('mutant')
