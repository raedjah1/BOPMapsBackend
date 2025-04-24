from django.shortcuts import render, redirect
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model, login
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import redirect
import requests
import json
import logging
from datetime import datetime, timedelta
import uuid
import string
import random

from .models import MusicService, RecentTrack
from .services import MusicServiceAuthMixin, SpotifyService
from .utils import (
    search_music, 
    get_recently_played_tracks, 
    get_user_playlists, 
    get_playlist_tracks,
    get_track_details
)

User = get_user_model()
logger = logging.getLogger('bopmaps')

# View Functions
@login_required
def connect_services(request):
    """Page for connecting music services"""
    return render(request, 'music/connect_services.html')

def spotify_auth(request):
    """Start Spotify OAuth flow"""
    auth_url = SpotifyService.get_auth_url(request)
    return redirect(auth_url)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def spotify_mobile_auth(request):
    """Start Spotify OAuth flow for mobile apps"""
    # Create a mock request to pass to get_auth_url with mobile redirect URI
    class MockRequest:
        def __init__(self):
            self.build_absolute_uri = lambda x: settings.SPOTIFY_MOBILE_REDIRECT_URI
    
    mock_request = MockRequest()
    auth_url = SpotifyService.get_auth_url(mock_request)
    return Response({'auth_url': auth_url})


def spotify_callback(request):
    """
    Handle Spotify OAuth callback
    This function can create a new user if one doesn't exist with the Spotify email
    """
    error = request.GET.get('error')
    if error:
        return JsonResponse({'error': error})
    
    code = request.GET.get('code')
    if not code:
        return JsonResponse({'error': 'No authorization code provided'})
    
    # Exchange code for tokens
    tokens_data = SpotifyService.exchange_code_for_tokens(request, code)
    
    if 'error' in tokens_data:
        return JsonResponse({'error': tokens_data['error']})
    
    # Create a temporary MusicService object to make API requests
    temp_service = MusicService(
        user=None,  # No user assigned yet
        service_type='spotify',
        access_token=tokens_data.get('access_token'),
        refresh_token=tokens_data.get('refresh_token', ''),
        expires_at=timezone.now() + timedelta(seconds=tokens_data.get('expires_in', 3600))
    )
    
    # Get user profile from Spotify
    user_profile = SpotifyService.make_api_request(temp_service, 'me')
    
    if 'error' in user_profile:
        return JsonResponse({'error': f"Failed to get Spotify profile: {user_profile['error']}"})
    
    # Check if we have a logged-in user
    if request.user.is_authenticated:
        # User is already logged in, just connect the service
        user = request.user
    else:
        # No logged-in user, check if a user with this email exists
        spotify_email = user_profile.get('email')
        
        if not spotify_email:
            return JsonResponse({'error': 'Spotify account does not have an email address'})
        
        try:
            # Try to find user with this email
            user = User.objects.get(email=spotify_email)
            # Auto-login the user
            login(request, user)
            logger.info(f"User {user.username} logged in via Spotify")
        except User.DoesNotExist:
            # User doesn't exist, create a new one
            try:
                # Generate a unique username based on Spotify display name
                display_name = user_profile.get('display_name', '')
                if not display_name:
                    display_name = "spotify_user"
                
                # Remove spaces and special characters, and make it lowercase
                base_username = ''.join(e for e in display_name if e.isalnum()).lower()
                
                # Check if username exists, if so, add random numbers
                if User.objects.filter(username=base_username).exists():
                    random_suffix = ''.join(random.choices(string.digits, k=4))
                    username = f"{base_username}_{random_suffix}"
                else:
                    username = base_username
                
                # Create the user with a random password
                random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
                
                # Get profile image if available
                profile_pic_url = None
                if user_profile.get('images') and len(user_profile['images']) > 0:
                    profile_pic_url = user_profile['images'][0].get('url')
                
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=spotify_email,
                    password=random_password,
                    # Don't set profile_pic here as it's a URL, not a file
                )
                
                # Set additional fields
                user.spotify_connected = True
                
                # Add Spotify profile info to user bio if available
                bio_parts = []
                if display_name:
                    bio_parts.append(f"Name: {display_name}")
                if user_profile.get('country'):
                    bio_parts.append(f"Country: {user_profile.get('country')}")
                if user_profile.get('product'):
                    product = user_profile.get('product').capitalize()
                    bio_parts.append(f"Spotify: {product}")
                
                if bio_parts:
                    user.bio = " | ".join(bio_parts)
                
                user.save()
                
                # Auto-login the user
                login(request, user)
                logger.info(f"New user {username} created and logged in via Spotify")
            except Exception as e:
                logger.error(f"Error creating user from Spotify: {str(e)}")
                return JsonResponse({'error': f"Failed to create user: {str(e)}"})
    
    # Save Spotify tokens to user's account
    user.spotify_connected = True
    user.save()
    MusicServiceAuthMixin.save_tokens(user, 'spotify', tokens_data)
    
    # Redirect to success page or frontend app
    return redirect('music:connection-success')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def callback_handler(request):
    """
    Handle OAuth callback from mobile app
    Accepts a JSON payload with the authorization code and exchanges it for tokens.
    This is used with the fixed redirect URI workflow.
    """
    try:
        # Get data from request
        code = request.data.get('code')
        if not code:
            return Response({'error': 'No authorization code provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a mock request to pass to exchange_code_for_tokens
        class MockRequest:
            def __init__(self):
                self.build_absolute_uri = lambda x: settings.SPOTIFY_MOBILE_REDIRECT_URI
        
        mock_request = MockRequest()
        
        # Exchange code for tokens
        tokens_data = SpotifyService.exchange_code_for_tokens(mock_request, code)
        
        if 'error' in tokens_data:
            logger.error(f"Error exchanging Spotify code: {tokens_data['error']}")
            return Response({'error': tokens_data['error']}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a temporary MusicService object to make API requests
        temp_service = MusicService(
            user=None,  # No user assigned yet
            service_type='spotify',
            access_token=tokens_data.get('access_token'),
            refresh_token=tokens_data.get('refresh_token', ''),
            expires_at=timezone.now() + timedelta(seconds=tokens_data.get('expires_in', 3600))
        )
        
        # Get user profile from Spotify
        user_profile = SpotifyService.make_api_request(temp_service, 'me')
        
        if 'error' in user_profile:
            logger.error(f"Error getting Spotify profile: {user_profile['error']}")
            return Response(
                {'error': f"Failed to get Spotify profile: {user_profile['error']}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use the authenticated user
        user = request.user
        
        # Save Spotify tokens to user's account
        user.spotify_connected = True
        user.save()
        service = MusicServiceAuthMixin.save_tokens(user, 'spotify', tokens_data)
        
        return Response({
            'message': 'Spotify connected successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'spotify_connected': user.spotify_connected
            },
            'service': {
                'service_type': service.service_type,
                'expires_at': service.expires_at
            }
        })
        
    except Exception as e:
        logger.error(f"Error in callback_handler: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@login_required
def connection_success(request):
    """Success page after connecting a music service"""
    return render(request, 'music/connection_success.html')


# REST API Viewsets
class MusicServiceViewSet(viewsets.ViewSet):
    """
    API endpoints for music service connections
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['GET'])
    def connected_services(self, request):
        """Get user's connected music services"""
        services = MusicService.objects.filter(user=request.user)
        data = [{'service_type': service.service_type, 
                 'connected_at': service.expires_at - timedelta(hours=1),  # Approximate connection time
                 'is_active': service.expires_at > timezone.now()
                } for service in services]
        return Response(data)
    
    @action(detail=False, methods=['DELETE'], url_path='disconnect/(?P<service_type>[^/.]+)')
    def disconnect_service(self, request, service_type=None):
        """Disconnect a music service"""
        if service_type not in dict(MusicService.SERVICE_TYPES):
            return Response(
                {"error": "Invalid service type"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = MusicService.objects.get(user=request.user, service_type=service_type)
            service.delete()
            return Response({"message": f"{service_type} disconnected successfully"})
        except MusicService.DoesNotExist:
            return Response(
                {"error": f"No {service_type} connection found"}, 
                status=status.HTTP_404_NOT_FOUND
            )


class SpotifyViewSet(viewsets.ViewSet):
    """
    API endpoints for Spotify integration
    """
    permission_classes = [IsAuthenticated]
    
    def _get_spotify_service(self):
        """Get the user's Spotify service or return None"""
        try:
            return MusicService.objects.get(user=self.request.user, service_type='spotify')
        except MusicService.DoesNotExist:
            return None
    
    @action(detail=False, methods=['GET'])
    def playlists(self, request):
        """Get user's Spotify playlists"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        limit = request.query_params.get('limit', 50)
        offset = request.query_params.get('offset', 0)
        
        result = SpotifyService.get_user_playlists(spotify_service, limit, offset)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result)
    
    @action(detail=True, methods=['GET'], url_path='playlist/(?P<playlist_id>[^/.]+)')
    def playlist(self, request, playlist_id=None):
        """Get a specific Spotify playlist"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        result = SpotifyService.get_playlist(spotify_service, playlist_id)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result)
    
    @action(detail=True, methods=['GET'], url_path='playlist/(?P<playlist_id>[^/.]+)/tracks')
    def playlist_tracks(self, request, playlist_id=None):
        """Get tracks from a Spotify playlist"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        limit = request.query_params.get('limit', 100)
        offset = request.query_params.get('offset', 0)
        
        result = SpotifyService.get_playlist_tracks(spotify_service, playlist_id, limit, offset)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result)
    
    @action(detail=True, methods=['GET'], url_path='track/(?P<track_id>[^/.]+)')
    def track(self, request, track_id=None):
        """Get details for a specific Spotify track"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        result = SpotifyService.get_track(spotify_service, track_id)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result)
    
    @action(detail=False, methods=['GET'])
    def recently_played(self, request):
        """Get user's recently played tracks on Spotify"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        limit = request.query_params.get('limit', 50)
        
        result = SpotifyService.get_recently_played(spotify_service, limit)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        # Optionally save to RecentTrack model
        if 'items' in result:
            for item in result['items']:
                track = item['track']
                RecentTrack.objects.update_or_create(
                    user=request.user,
                    track_id=track['id'],
                    service='spotify',
                    defaults={
                        'title': track['name'],
                        'artist': track['artists'][0]['name'],
                        'album': track['album']['name'],
                        'album_art': track['album']['images'][0]['url'] if track['album']['images'] else None,
                        'played_at': datetime.strptime(item['played_at'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    }
                )
        
        return Response(result)
    
    @action(detail=False, methods=['GET'])
    def search(self, request):
        """Search for tracks on Spotify"""
        spotify_service = self._get_spotify_service()
        if not spotify_service:
            return Response({"error": "Spotify not connected"}, status=status.HTTP_400_BAD_REQUEST)
        
        query = request.query_params.get('q', '')
        if not query:
            return Response({"error": "Search query is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        limit = request.query_params.get('limit', 20)
        
        result = SpotifyService.search_tracks(spotify_service, query, limit)
        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(result)


class MusicTrackSerializer(serializers.Serializer):
    """Serializer for music track data"""
    id = serializers.CharField()
    title = serializers.CharField()
    artist = serializers.CharField()
    album = serializers.CharField(required=False, allow_null=True)
    album_art = serializers.URLField(required=False, allow_null=True)
    url = serializers.URLField()
    service = serializers.CharField()
    preview_url = serializers.URLField(required=False, allow_null=True)


class MusicTrackViewSet(viewsets.ViewSet):
    """
    API endpoints for selecting music tracks for pins
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['GET'])
    def search(self, request):
        """Search for music tracks"""
        query = request.query_params.get('q', '')
        service = request.query_params.get('service', None)
        limit = int(request.query_params.get('limit', 10))
        
        if not query:
            return Response(
                {"error": "Search query is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = search_music(request.user, query, service, limit)
        return Response(results)
    
    @action(detail=False, methods=['GET'])
    def recently_played(self, request):
        """Get user's recently played tracks"""
        service = request.query_params.get('service', None)
        limit = int(request.query_params.get('limit', 10))
        
        results = get_recently_played_tracks(request.user, service, limit)
        return Response(results)
    
    @action(detail=False, methods=['GET'])
    def playlists(self, request):
        """Get user's playlists"""
        service = request.query_params.get('service', None)
        limit = int(request.query_params.get('limit', 20))
        
        results = get_user_playlists(request.user, service, limit)
        return Response(results)
    
    @action(detail=False, methods=['GET'], url_path='playlist/(?P<service>[^/.]+)/(?P<playlist_id>[^/.]+)')
    def playlist_tracks(self, request, service=None, playlist_id=None):
        """Get tracks from a playlist"""
        if not service or not playlist_id:
            return Response(
                {"error": "Service and playlist ID are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        limit = int(request.query_params.get('limit', 50))
        
        results = get_playlist_tracks(request.user, playlist_id, service, limit)
        if results is None:
            return Response(
                {"error": f"Unable to retrieve playlist tracks from {service}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(results)
    
    @action(detail=False, methods=['GET'], url_path='track/(?P<service>[^/.]+)/(?P<track_id>[^/.]+)')
    def track_details(self, request, service=None, track_id=None):
        """Get details for a specific track"""
        if not service or not track_id:
            return Response(
                {"error": "Service and track ID are required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = get_track_details(request.user, track_id, service)
        if result is None:
            return Response(
                {"error": f"Unable to retrieve track details from {service}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(result)
