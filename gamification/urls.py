from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AchievementViewSet, PinSkinViewSet, UserAchievementViewSet

router = DefaultRouter()
# Register your viewsets here:
router.register(r'achievements', AchievementViewSet, basename='achievements')
router.register(r'skins', PinSkinViewSet, basename='skins')
router.register(r'user-achievements', UserAchievementViewSet, basename='user-achievements')

urlpatterns = [
    path('', include(router.urls)),
]

app_name = 'gamification' 