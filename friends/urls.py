from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FriendViewSet, FriendRequestViewSet

router = DefaultRouter()
# Register your viewsets here:
router.register(r'', FriendViewSet, basename='friends')
router.register(r'requests', FriendRequestViewSet, basename='friend-requests')

urlpatterns = [
    path('', include(router.urls)),
] 