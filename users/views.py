from django.shortcuts import render
from rest_framework import status, permissions, viewsets, generics
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from .serializers import (
    UserSerializer, UserUpdateSerializer, UserRegistrationSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from bopmaps.views import BaseModelViewSet
from bopmaps.permissions import IsOwnerOrReadOnly, IsOwner
from bopmaps.utils import create_error_response
import logging

User = get_user_model()
logger = logging.getLogger('bopmaps')

class UserViewSet(BaseModelViewSet):
    """
    API viewset for user management.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Additional filters can be added here
        return queryset
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserRegistrationSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return super().get_permissions()
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Get the current user's profile
        """
        try:
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving user profile: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['put', 'patch'])
    def update_profile(self, request):
        """
        Update the current user's profile
        """
        try:
            serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating user profile: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def update_location(self, request):
        """
        Update the current user's location
        """
        try:
            lat = request.data.get('latitude')
            lng = request.data.get('longitude')
            
            if not lat or not lng:
                return create_error_response("Latitude and longitude are required", status.HTTP_400_BAD_REQUEST)
            
            try:
                point = Point(float(lng), float(lat), srid=4326)
            except (ValueError, TypeError):
                return create_error_response("Invalid coordinates", status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                request.user.location = point
                request.user.last_location_update = timezone.now()
                request.user.save(update_fields=['location', 'last_location_update'])
                
            return Response({
                "success": True,
                "message": "Location updated successfully",
                "location": {
                    "latitude": lat,
                    "longitude": lng,
                    "updated_at": request.user.last_location_update
                }
            })
        except Exception as e:
            logger.error(f"Error updating user location: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def update_fcm_token(self, request):
        """
        Update the user's FCM token for push notifications
        """
        try:
            fcm_token = request.data.get('fcm_token')
            if not fcm_token:
                return create_error_response("FCM token is required", status.HTTP_400_BAD_REQUEST)
            
            with transaction.atomic():
                request.user.fcm_token = fcm_token
                request.user.save(update_fields=['fcm_token'])
                
            return Response({
                "success": True,
                "message": "FCM token updated successfully"
            })
        except Exception as e:
            logger.error(f"Error updating FCM token: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


class AuthTokenObtainPairView(TokenObtainPairView):
    """
    Custom token obtain pair view with extra data
    """
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            try:
                # Add user data to response
                username = request.data.get('username')
                user = User.objects.get(username=username)
                user_data = UserSerializer(user).data
                
                # Update response with user data
                data = response.data
                data['user'] = user_data
                
                # Update last active
                user.update_last_active()
                
                return Response(data)
            except User.DoesNotExist:
                logger.error(f"User not found during token obtain: {username}")
            except Exception as e:
                logger.error(f"Error adding user data to token response: {str(e)}")
                
        return response


class RegistrationView(generics.CreateAPIView):
    """
    API view for user registration
    """
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    user = serializer.save()
                    
                    # Generate JWT tokens
                    refresh = RefreshToken.for_user(user)
                    
                    return Response({
                        'message': 'User registered successfully',
                        'user': UserSerializer(user).data,
                        'tokens': {
                            'refresh': str(refresh),
                            'access': str(refresh.access_token),
                        }
                    }, status=status.HTTP_201_CREATED)
            except Exception as e:
                logger.error(f"Error during user registration: {str(e)}")
                return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetRequestView(generics.GenericAPIView):
    """
    API view to request a password reset
    """
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            try:
                user = User.objects.get(email=email)
                
                # Generate token here and send email with reset link
                # In a real implementation, you'd use a dedicated service for this
                
                return Response({
                    'message': 'Password reset email sent'
                })
            except User.DoesNotExist:
                # Don't reveal that the user doesn't exist for security
                logger.info(f"Password reset requested for non-existent email: {email}")
                return Response({
                    'message': 'Password reset email sent if the email exists'
                })
            except Exception as e:
                logger.error(f"Error sending password reset: {str(e)}")
                return create_error_response("Error processing request", status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(generics.GenericAPIView):
    """
    API view to confirm a password reset
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            token = serializer.validated_data['token']
            password = serializer.validated_data['password']
            
            # Validate token and update password
            # This is a simplified example, actual implementation would verify the token
            
            try:
                # In a real implementation, decode the token and find the user
                # user = User.objects.get(pk=user_id_from_token)
                # user.set_password(password)
                # user.save()
                
                return Response({
                    'message': 'Password reset successful'
                })
            except Exception as e:
                logger.error(f"Error confirming password reset: {str(e)}")
                return create_error_response("Invalid or expired token", status.HTTP_400_BAD_REQUEST)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    API view to logout a user by invalidating their refresh token
    """
    try:
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return create_error_response("Refresh token is required", status.HTTP_400_BAD_REQUEST)
            
        token = RefreshToken(refresh_token)
        token.blacklist()
        
        return Response({
            'message': 'Logout successful'
        })
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        return create_error_response(str(e), status.HTTP_400_BAD_REQUEST)
