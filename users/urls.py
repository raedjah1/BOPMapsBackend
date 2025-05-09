from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserViewSet, AuthTokenObtainPairView, RegistrationView,
    PasswordResetRequestView, PasswordResetConfirmView, logout_view
)

# Create a router for viewsets
router = DefaultRouter()
router.register(r'', UserViewSet)

urlpatterns = [
    # ViewSet routes
    path('', include(router.urls)),
    
    # Auth routes
    path('auth/token/', AuthTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', RegistrationView.as_view(), name='register'),
    path('auth/logout', logout_view, name='logout-no-slash'),
    path('auth/logout/', logout_view, name='logout'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    
    # User profile endpoints are handled by the viewset's actions
    # (me/, update_profile/, update_location/, update_fcm_token/)
] 