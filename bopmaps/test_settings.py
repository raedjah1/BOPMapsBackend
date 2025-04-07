"""
Django test settings for the BOPMaps project.
Overrides main settings for testing.
"""

from .settings import *

# Use in-memory SQLite database for testing
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.spatialite',
        'NAME': ':memory:',
    }
}

# Disable migrations during tests for faster test runs
MIGRATION_MODULES = {app.split('.')[-1]: 'bopmaps.tests.migrations' for app in INSTALLED_APPS}

# Use faster password hasher for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable token blacklist checks during tests
SIMPLE_JWT = {
    **SIMPLE_JWT,
    'BLACKLIST_AFTER_ROTATION': False,
}

# Disable throttling for tests
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon': None,
        'user': None,
    },
}

# Use console email backend for testing
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable cache for tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

# Turn off middleware that we don't need for tests
MIDDLEWARE = [m for m in MIDDLEWARE if not (
    m.startswith('debug_toolbar') or
    m.startswith('bopmaps.middleware.RequestLogMiddleware') or
    m.startswith('bopmaps.middleware.UpdateLastActivityMiddleware')
)]

# Use a simpler logging setup for tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['null'],
            'propagate': False,
            'level': 'INFO',
        },
        'bopmaps': {
            'handlers': ['null'],
            'propagate': False,
            'level': 'INFO',
        },
    }
} 