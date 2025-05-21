from django.http import HttpResponse
from django.urls import path
from django.conf import settings
from django.core.management import execute_from_command_line
import os
import sys


def home(request):
    return HttpResponse("""
    <h1>Welcome to BOPMaps Backend!</h1>
    <p>The Django server is running successfully.</p>
    <p>This is a simplified test version to verify Django is working correctly.</p>
    """)


if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test_secret_key',
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
        ],
    )

urlpatterns = [
    path('', home),
]

if __name__ == '__main__':
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    execute_from_command_line(sys.argv) 