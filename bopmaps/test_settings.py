"""
Django test settings for the BOPMaps project.
Overrides main settings for testing.
"""

from .settings import *
import os

# Use a file-based SQLite database for testing instead of in-memory
DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.spatialite',
        'NAME': os.path.join(BASE_DIR, 'test_db.sqlite3'),
        'TEST': {
            'NAME': os.path.join(BASE_DIR, 'test_db.sqlite3'),
        }
    }
}

# Ensure test database is created and migrations are applied
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# Comment out the migration disabling as it's causing issues
# Instead we'll just use the regular migrations during tests
#MIGRATION_MODULES = {app.split('.')[-1]: 'bopmaps.tests.migrations' for app in INSTALLED_APPS}

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

# Disable cache for tests, but provide all required settings
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'dummy-cache',
    },
    'sessions': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'dummy-sessions',
    }
}

# Use memory sessions for testing
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_CACHE_ALIAS = 'default'

# Disable debug toolbar in tests
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']

# Ensure middleware order is correct for sessions and CSRF and remove debug toolbar
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # This must come before CSRF middleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

# Add a root directory for static files to prevent warnings
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles_test')

# Configure static files for tests
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

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