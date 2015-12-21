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
    INSTALLED_APPS.append('mutant.contrib.boolean')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]
