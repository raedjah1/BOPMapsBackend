from django.shortcuts import render, redirect
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

import requests
import json
from datetime import datetime, timedelta

from .models import MusicService, RecentTrack
from .services import MusicServiceAuthMixin, SpotifyService
from .utils import (
    search_music, 
    get_recently_played_tracks, 
    get_user_playlists, 
    get_playlist_tracks,
    get_track_details
)

# View Functions
@login_required
def connect_services(request):
    """Page for connecting music services"""
    return render(request, 'music/connect_services.html')

@login_required
def spotify_auth(request):
    """Start Spotify OAuth flow"""
    auth_url = SpotifyService.get_auth_url(request)
    return redirect(auth_url)


@login_required
def spotify_callback(request):
    """Handle Spotify OAuth callback"""
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
    
    # Save tokens to database
    MusicServiceAuthMixin.save_tokens(request.user, 'spotify', tokens_data)
    
    # Redirect to success page or frontend app
    return redirect('music:connection-success')


@login_required
def connection_success(request):
    """Simple success page after connecting a music service"""
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
