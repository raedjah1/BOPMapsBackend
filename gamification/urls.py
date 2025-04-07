from django.urls import path, include
from rest_framework.routers import DefaultRouter
# from .views import AchievementViewSet, BadgeViewSet  # Uncomment when views are implemented

router = DefaultRouter()
# Register your viewsets here:
# router.register(r'achievements', AchievementViewSet, basename='achievements')
# router.register(r'badges', BadgeViewSet, basename='badges')

urlpatterns = [
    path('', include(router.urls)),
] 