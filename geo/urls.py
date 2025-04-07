from django.urls import path, include
from rest_framework.routers import DefaultRouter
# from .views import LocationViewSet  # Uncomment when views are implemented

router = DefaultRouter()
# Register your viewsets here:
# router.register(r'locations', LocationViewSet, basename='locations')

urlpatterns = [
    path('', include(router.urls)),
] 