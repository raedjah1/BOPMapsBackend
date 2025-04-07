"""
Music service API integration classes
"""
import base64
import requests
from datetime import timedelta
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
import urllib.parse

# Base classes for music service integrations
class MusicServiceAuthMixin:
    """Base mixin for music service authentication"""
    
    @staticmethod
    def get_redirect_uri(request, service):
        """Get the redirect URI for OAuth flow"""
        return request.build_absolute_uri(reverse(f'music:{service}-callback'))
    
    @staticmethod
    def save_tokens(user, service_type, tokens_data):
        """Save authentication tokens to the database"""
        from .models import MusicService  # Import here to avoid circular imports
        
        expires_at = timezone.now() + timedelta(seconds=tokens_data.get('expires_in', 3600))
        
        # Update existing or create new
        music_service, created = MusicService.objects.update_or_create(
            user=user,
            service_type=service_type,
            defaults={
                'access_token': tokens_data.get('access_token'),
                'refresh_token': tokens_data.get('refresh_token', ''),
                'expires_at': expires_at
            }
        )
        return music_service

# Spotify Integration
class SpotifyService:
    """Spotify API service implementation"""
    AUTHORIZATION_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE_URL = "https://api.spotify.com/v1"
    
    @staticmethod
    def get_auth_url(request):
        """Generate Spotify authorization URL"""
        redirect_uri = MusicServiceAuthMixin.get_redirect_uri(request, 'spotify')
        
        params = {
            'client_id': settings.SPOTIFY_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': 'user-read-private user-read-email playlist-read-private user-library-read user-read-recently-played',
        }
        
        return f"{SpotifyService.AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"
    
    @staticmethod
    def exchange_code_for_tokens(request, code):
        """Exchange authorization code for tokens"""
        redirect_uri = MusicServiceAuthMixin.get_redirect_uri(request, 'spotify')
        
        # Prepare auth header
        auth_header = base64.b64encode(
            f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()
        
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri
        }
        
        response = requests.post(SpotifyService.TOKEN_URL, headers=headers, data=data)
        return response.json()
    
    @staticmethod
    def refresh_access_token(music_service):
        """Refresh expired access token"""
        # Prepare auth header
        auth_header = base64.b64encode(
            f"{settings.SPOTIFY_CLIENT_ID}:{settings.SPOTIFY_CLIENT_SECRET}".encode()
        ).decode()
        
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': music_service.refresh_token
        }
        
        response = requests.post(SpotifyService.TOKEN_URL, headers=headers, data=data)
        if response.status_code == 200:
            tokens_data = response.json()
            # Update token data
            music_service.access_token = tokens_data['access_token']
            if 'refresh_token' in tokens_data:
                music_service.refresh_token = tokens_data['refresh_token']
            music_service.expires_at = timezone.now() + timedelta(seconds=tokens_data.get('expires_in', 3600))
            music_service.save()
            return True
        return False
    
    @staticmethod
    def make_api_request(music_service, endpoint, method='GET', data=None):
        """Make authenticated request to Spotify API"""
        # Check if token is expired and refresh if needed
        if music_service.expires_at <= timezone.now():
            success = SpotifyService.refresh_access_token(music_service)
            if not success:
                return {'error': 'Failed to refresh access token'}
        
        headers = {
            'Authorization': f'Bearer {music_service.access_token}'
        }
        
        url = f"{SpotifyService.API_BASE_URL}/{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            headers['Content-Type'] = 'application/json'
            response = requests.post(url, headers=headers, json=data)
        elif method == 'PUT':
            headers['Content-Type'] = 'application/json'
            response = requests.put(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            return {'error': 'Invalid method'}
            
        if response.status_code in (200, 201):
            return response.json()
        else:
            return {'error': f'API error: {response.status_code}', 'details': response.text}
    
    @staticmethod
    def get_user_playlists(music_service, limit=50, offset=0):
        """Get user's playlists"""
        return SpotifyService.make_api_request(
            music_service, 
            f"me/playlists?limit={limit}&offset={offset}"
        )
    
    @staticmethod
    def get_playlist(music_service, playlist_id):
        """Get a specific playlist"""
        return SpotifyService.make_api_request(music_service, f"playlists/{playlist_id}")
    
    @staticmethod
    def get_playlist_tracks(music_service, playlist_id, limit=100, offset=0):
        """Get tracks from a playlist"""
        return SpotifyService.make_api_request(
            music_service, 
            f"playlists/{playlist_id}/tracks?limit={limit}&offset={offset}"
        )
    
    @staticmethod
    def get_track(music_service, track_id):
        """Get details for a specific track"""
        return SpotifyService.make_api_request(music_service, f"tracks/{track_id}")
    
    @staticmethod
    def get_recently_played(music_service, limit=50):
        """Get user's recently played tracks"""
        return SpotifyService.make_api_request(
            music_service, 
            f"me/player/recently-played?limit={limit}"
        )
    
    @staticmethod
    def search_tracks(music_service, query, limit=20):
        """Search for tracks"""
        encoded_query = urllib.parse.quote(query)
        return SpotifyService.make_api_request(
            music_service, 
            f"search?q={encoded_query}&type=track&limit={limit}"
        ) 