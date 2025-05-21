"""
URL configuration for bopmaps project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import TokenVerifyView
from django.views.generic.base import RedirectView
from .admin import bopmaps_admin_site
from .views import IndexView
from music.views import spotify_callback

# Import admin registrations to ensure they're loaded
from . import admin_registrations

urlpatterns = [
    # Landing page
    path('', IndexView.as_view(), name='index'),
    
    # Spotify Callback URL - to match what's likely in Spotify Developer Dashboard
    path('callback/', spotify_callback, name='spotify_callback_root'),
    
    # Admin - with custom admin site
    path('admin/', bopmaps_admin_site.urls),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # JWT Authentication endpoints
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # App URLs
    path('api/users/', include('users.urls')),
    path('api/pins/', include('pins.urls')),
    path('api/friends/', include('friends.urls')),
    path('api/music/', include('music.urls')),
    path('api/gamification/', include('gamification.urls')),
    path('api/geo/', include('geo.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Enable the debug toolbar in development, but not during tests
    import sys
    if 'test' not in sys.argv: # Check if 'test' command is being run
        try:
            import debug_toolbar
            urlpatterns.append(path('__debug__/', include(debug_toolbar.urls)))
        except ImportError:
            pass
