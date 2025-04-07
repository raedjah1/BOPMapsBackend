from django.urls import path, include
from rest_framework.routers import DefaultRouter
# from .views import MusicTrackViewSet, MusicProviderViewSet  # Uncomment when views are implemented

router = DefaultRouter()
# Register your viewsets here:
# router.register(r'tracks', MusicTrackViewSet, basename='tracks')
# router.register(r'providers', MusicProviderViewSet, basename='providers')

urlpatterns = [
    path('', include(router.urls)),
] 