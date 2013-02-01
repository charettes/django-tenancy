from . import INSTALLED_APPS, SECRET_KEY


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'tenancy',
        'USER': 'postgres'
    }
}