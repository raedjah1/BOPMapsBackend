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
    
    # Additional endpoints are handled by the viewset's actions:
    # Standard endpoints:
    # - /api/pins/{id}/            - CRUD operations on pins
    # - /api/pins/list_map/        - Get pins optimized for map display
    # - /api/pins/nearby/          - Get pins near a location
    # - /api/pins/trending/        - Get trending pins
    # - /api/pins/{id}/view/       - Record pin view
    # - /api/pins/{id}/like/       - Record pin like
    # - /api/pins/{id}/collect/    - Record pin collect
    # - /api/pins/{id}/share/      - Record pin share
    # - /api/pins/{id}/map_details/ - Get detailed pin info for map
    
    # New enhanced endpoints:
    # - /api/pins/recommended/     - Get personalized pin recommendations
    # - /api/pins/advanced_search/ - Advanced pin search
    # - /api/pins/{id}/similar/    - Find similar pins
    # - /api/pins/{id}/analytics/  - Get pin analytics (owner only)
    # - /api/pins/websocket_connect/ - Get WebSocket connection info
    # - /api/pins/batch_interact/ - Process multiple pin interactions
] 