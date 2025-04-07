from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PinViewSet, PinInteractionViewSet

# Create a router for viewsets
router = DefaultRouter()
router.register(r'', PinViewSet)
router.register(r'interactions', PinInteractionViewSet)

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),
    
    # Additional endpoints are handled by the viewset's actions
    # (nearby/, trending/, list_map/, view/, like/, collect/, share/)
] 