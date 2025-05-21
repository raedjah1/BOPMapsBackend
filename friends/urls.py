from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FriendViewSet, FriendRequestViewSet

app_name = 'friends'

router = DefaultRouter()
# Register more specific routes first
router.register(r'requests', FriendRequestViewSet, basename='friend-requests')
router.register(r'', FriendViewSet, basename='friends')

urlpatterns = [
    path('', include(router.urls)),
] 