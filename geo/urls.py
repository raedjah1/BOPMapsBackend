from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TrendingAreaViewSet, UserLocationViewSet, 
    BuildingViewSet, RoadViewSet, ParkViewSet,
    UserMapSettingsViewSet, OSMTileView
)
from .region_views import RegionViewSet, RegionBundleTaskView

router = DefaultRouter()
# Register viewsets
router.register(r'trending', TrendingAreaViewSet, basename='trending')
router.register(r'locations', UserLocationViewSet, basename='locations')
router.register(r'buildings', BuildingViewSet, basename='buildings')
router.register(r'roads', RoadViewSet, basename='roads')
router.register(r'parks', ParkViewSet, basename='parks')
router.register(r'settings', UserMapSettingsViewSet, basename='map-settings')
router.register(r'regions', RegionViewSet, basename='regions')

urlpatterns = [
    path('', include(router.urls)),
    # Tile proxy URL pattern
    path('tiles/osm/<int:z>/<int:x>/<int:y>.png', OSMTileView.as_view(), name='osm-tile'),
    # Region bundle APIs
    path('regions/bundle/', RegionBundleTaskView.as_view(), name='region-bundle-create'),
    path('regions/bundle/<str:task_id>/', RegionBundleTaskView.as_view(), name='region-bundle-status'),
] 