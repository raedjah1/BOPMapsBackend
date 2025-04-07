from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TrendingAreaViewSet, UserLocationViewSet

router = DefaultRouter()
# Register viewsets
router.register(r'trending', TrendingAreaViewSet, basename='trending')
router.register(r'locations', UserLocationViewSet, basename='locations')

urlpatterns = [
    path('', include(router.urls)),
] 