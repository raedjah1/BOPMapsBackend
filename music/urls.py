from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    spotify_auth, 
    spotify_callback, 
    connection_success,
    connect_services,
    MusicServiceViewSet,
    SpotifyViewSet,
    MusicTrackViewSet,
    callback_handler
)

router = DefaultRouter()
# Register viewsets
router.register(r'services', MusicServiceViewSet, basename='services')
router.register(r'spotify', SpotifyViewSet, basename='spotify')
router.register(r'tracks', MusicTrackViewSet, basename='tracks')

urlpatterns = [
    # Main view
    path('connect/', connect_services, name='connect-services'),
    
    # OAuth flow endpoints
    path('auth/spotify/', spotify_auth, name='spotify-auth'),
    path('auth/spotify/callback/', spotify_callback, name='spotify-callback'),
    path('auth/success/', connection_success, name='connection-success'),
    
    # Mobile app callback handler
    path('auth/callback/', callback_handler, name='callback-handler'),
    
    # API endpoints
    path('api/', include(router.urls)),
] 