from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PinViewSet, PinInteractionViewSet

# Create a router for viewsets
router = DefaultRouter()
# Register PinInteractionViewSet first with a specific basename
router.register(r'interactions', PinInteractionViewSet, basename='pininteraction')
# Register PinViewSet after with an explicit basename
router.register(r'', PinViewSet, basename='pin')

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),
    
    # Additional endpoints are handled by the viewset's actions
    # (nearby/, trending/, list_map/, view/, like/, collect/, share/)
] 