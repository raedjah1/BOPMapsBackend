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
import jwt
import time
import logging

logger = logging.getLogger('bopmaps')

# Base classes for music service integrations
class MusicServiceAuthMixin:
    """Base mixin for music service authentication"""
    
    @staticmethod
    def get_redirect_uri(request, service):
        """Get the redirect URI for OAuth flow"""
        # Check if a fixed redirect URI is defined in settings for this service
        setting_name = f'{service.upper()}_REDIRECT_URI'
        fixed_uri = getattr(settings, setting_name, None)
        if fixed_uri:
            return fixed_uri
        
        # Fall back to dynamically generated URI based on the request
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
        
    @staticmethod
    def get_saved_tracks(music_service, limit=50, offset=0):
        """Get user's saved/liked tracks"""
        return SpotifyService.make_api_request(
            music_service, 
            f"me/tracks?limit={limit}&offset={offset}"
        )

# Apple Music Integration
class AppleMusicService:
    """Apple Music API service implementation"""
    API_BASE_URL = "https://api.music.apple.com/v1"
    
    @staticmethod
    def get_developer_token():
        """Generate a developer token for Apple Music API"""
        # This is done through a JWT generator using the Apple Music private key
        # The developer token is used for API requests but doesn't authorize a specific user
        key_id = settings.APPLE_MUSIC_KEY_ID
        team_id = settings.APPLE_MUSIC_TEAM_ID
        private_key = settings.APPLE_MUSIC_PRIVATE_KEY
        
        # Make private key usable by PyJWT
        # The private key is stored as a string in settings, potentially with escaped newlines
        # We need to replace any '\n' with actual newlines
        if private_key.startswith('"') and private_key.endswith('"'):
            private_key = private_key[1:-1]
        private_key = private_key.replace('\\n', '\n')
        
        headers = {
            'alg': 'ES256',
            'kid': key_id
        }
        
        payload = {
            'iss': team_id,
            'iat': int(time.time()),
            'exp': int(time.time()) + 15777000  # 6 months
        }
        
        try:
            token = jwt.encode(payload, private_key, algorithm='ES256', headers=headers)
            # Ensure we return a string (PyJWT >= 2.0.0 returns a string, < 2.0.0 returns bytes)
            if isinstance(token, bytes):
                return token.decode('utf-8')
            return token
        except Exception as e:
            # Log the error for debugging
            logger.error(f"Error generating Apple Music developer token: {str(e)}")
            # Return a placeholder for development if there's an error
            if settings.DEBUG:
                return "DEVELOPER_TOKEN_PLACEHOLDER_DEBUG_MODE"
            raise
    
    @staticmethod
    def validate_user_token(user_token):
        """Validate a user token received from the mobile client"""
        # In Apple Music integration, the mobile app handles user authentication
        # and provides a user token which we validate here
        # A basic validation would check if the token is not empty and has a reasonable length
        if not user_token or len(user_token) < 20:
            return False
        
        # In a production environment, you might make a test API call with the token
        # to validate it. For now, we'll just do basic checks.
        return True
    
    @staticmethod
    def save_user_token(user, user_token):
        """Save the Apple Music user token to the database"""
        from .models import MusicService  # Import here to avoid circular imports
        
        # Apple Music tokens typically expire after a few months
        # We'll set a 6-month expiry as a reasonable default
        expires_at = timezone.now() + timedelta(days=180)
        
        # Update existing or create new
        music_service, created = MusicService.objects.update_or_create(
            user=user,
            service_type='apple',
            defaults={
                'access_token': user_token,
                # Apple Music doesn't use refresh tokens like OAuth
                'refresh_token': '',
                'expires_at': expires_at
            }
        )
        return music_service
    
    @staticmethod
    def make_api_request(music_service, endpoint, method='GET', data=None):
        """Make authenticated request to Apple Music API"""
        # Apple Music API requires both a developer token and a user token
        developer_token = AppleMusicService.get_developer_token()
        user_token = music_service.access_token
        
        headers = {
            'Authorization': f'Bearer {developer_token}',
            'Music-User-Token': user_token
        }
        
        url = f"{AppleMusicService.API_BASE_URL}/{endpoint}"
        
        if method == 'GET':
            response = requests.get(url, headers=headers)
        elif method == 'POST':
            headers['Content-Type'] = 'application/json'
            response = requests.post(url, headers=headers, json=data)
        # Other methods as needed
        
        if response.status_code in (200, 201):
            return response.json()
        else:
            return {'error': f'API error: {response.status_code}', 'details': response.text}
    
    @staticmethod
    def search_tracks(music_service, query, limit=20):
        """Search for tracks"""
        encoded_query = urllib.parse.quote(query)
        return AppleMusicService.make_api_request(
            music_service, 
            f"catalog/us/search?term={encoded_query}&types=songs&limit={limit}"
        )
    
    @staticmethod
    def get_recently_played(music_service, limit=50):
        """Get user's recently played tracks"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"me/recent/played?limit={limit}"
        )
    
    @staticmethod
    def get_user_playlists(music_service, limit=50, offset=0):
        """Get user's playlists"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"me/library/playlists?limit={limit}&offset={offset}"
        )
    
    @staticmethod
    def get_playlist(music_service, playlist_id):
        """Get a specific playlist"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"me/library/playlists/{playlist_id}"
        )
    
    @staticmethod
    def get_playlist_tracks(music_service, playlist_id, limit=100, offset=0):
        """Get tracks from a playlist"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"me/library/playlists/{playlist_id}/tracks?limit={limit}&offset={offset}"
        )
    
    @staticmethod
    def get_track(music_service, track_id):
        """Get details for a specific track"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"catalog/us/songs/{track_id}"
        )
    
    @staticmethod
    def get_saved_tracks(music_service, limit=50, offset=0):
        """Get user's saved/liked tracks"""
        return AppleMusicService.make_api_request(
            music_service, 
            f"me/library/songs?limit={limit}&offset={offset}"
        ) 