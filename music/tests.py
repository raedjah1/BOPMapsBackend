from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from .models import MusicService
from .services import SpotifyService, AppleMusicService, SoundCloudService

User = get_user_model()

class MusicServiceTestCase(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create test music services
        self.spotify_service = MusicService.objects.create(
            user=self.user,
            service_type='spotify',
            access_token='spotify_token',
            refresh_token='spotify_refresh',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        self.apple_service = MusicService.objects.create(
            user=self.user,
            service_type='apple',
            access_token='apple_token',
            refresh_token='',  # Apple Music doesn't use refresh tokens
            expires_at=timezone.now() + timedelta(days=180)
        )
        
        self.soundcloud_service = MusicService.objects.create(
            user=self.user,
            service_type='soundcloud',
            access_token='soundcloud_token',
            refresh_token='',  # SoundCloud tokens don't expire
            expires_at=timezone.now() + timedelta(days=365)
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_connected_services(self):
        """Test listing connected music services"""
        url = reverse('music:services-connected-services')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        
        # Check service types
        service_types = [service['service_type'] for service in response.data]
        self.assertIn('spotify', service_types)
        self.assertIn('apple', service_types)
        self.assertIn('soundcloud', service_types)
        
    def test_disconnect_service(self):
        """Test disconnecting a music service"""
        url = reverse('music:services-disconnect-service', kwargs={'service_type': 'spotify'})
        response = self.client.delete(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check that service was removed
        self.assertFalse(MusicService.objects.filter(
            user=self.user,
            service_type='spotify'
        ).exists())

class SpotifyServiceTestCase(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user with Spotify service
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        self.spotify_service = MusicService.objects.create(
            user=self.user,
            service_type='spotify',
            access_token='spotify_token',
            refresh_token='spotify_refresh',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    @patch('music.services.SpotifyService.get_user_playlists')
    def test_get_spotify_playlists(self, mock_get_playlists):
        """Test getting Spotify playlists"""
        # Mock Spotify API response
        mock_response = {
            'items': [
                {
                    'id': 'playlist1',
                    'name': 'Test Playlist',
                    'images': [{'url': 'http://example.com/image.jpg'}],
                    'tracks': {'total': 10},
                    'external_urls': {'spotify': 'http://spotify.com/playlist1'}
                }
            ]
        }
        mock_get_playlists.return_value = mock_response
        
        url = reverse('music:spotify-playlists')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)
        
    @patch('music.services.SpotifyService.search_tracks')
    def test_search_spotify_tracks(self, mock_search):
        """Test searching for Spotify tracks"""
        # Mock Spotify API response
        mock_response = {
            'tracks': {
                'items': [
                    {
                        'id': 'track1',
                        'name': 'Test Track',
                        'artists': [{'name': 'Test Artist'}],
                        'album': {
                            'name': 'Test Album',
                            'images': [{'url': 'http://example.com/album.jpg'}]
                        },
                        'external_urls': {'spotify': 'http://spotify.com/track1'}
                    }
                ]
            }
        }
        mock_search.return_value = mock_response
        
        url = reverse('music:spotify-search')
        response = self.client.get(url, {'q': 'test'})
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)

class AppleMusicServiceTestCase(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user with Apple Music service
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        self.apple_service = MusicService.objects.create(
            user=self.user,
            service_type='apple',
            access_token='apple_token',
            refresh_token='',
            expires_at=timezone.now() + timedelta(days=180)
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    @patch('music.services.AppleMusicService.get_user_playlists')
    def test_get_apple_music_playlists(self, mock_get_playlists):
        """Test getting Apple Music playlists"""
        # Mock Apple Music API response
        mock_response = {
            'data': [
                {
                    'id': 'playlist1',
                    'attributes': {
                        'name': 'Test Playlist',
                        'artwork': {'url': 'http://example.com/image.jpg'},
                        'trackCount': 10,
                        'url': 'http://apple.com/playlist1'
                    }
                }
            ]
        }
        mock_get_playlists.return_value = mock_response
        
        url = reverse('music:apple-playlists')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)
        
    @patch('music.services.AppleMusicService.search_tracks')
    def test_search_apple_music_tracks(self, mock_search):
        """Test searching for Apple Music tracks"""
        # Mock Apple Music API response
        mock_response = {
            'results': {
                'songs': {
                    'data': [
                        {
                            'id': 'track1',
                            'attributes': {
                                'name': 'Test Track',
                                'artistName': 'Test Artist',
                                'albumName': 'Test Album',
                                'artwork': {'url': 'http://example.com/album.jpg'}
                            }
                        }
                    ]
                }
            }
        }
        mock_search.return_value = mock_response
        
        url = reverse('music:apple-search')
        response = self.client.get(url, {'q': 'test'})
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)

class SoundCloudServiceTestCase(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user with SoundCloud service
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        self.soundcloud_service = MusicService.objects.create(
            user=self.user,
            service_type='soundcloud',
            access_token='soundcloud_token',
            refresh_token='',
            expires_at=timezone.now() + timedelta(days=365)
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    @patch('music.services.SoundCloudService.get_user_playlists')
    def test_get_soundcloud_playlists(self, mock_get_playlists):
        """Test getting SoundCloud playlists"""
        # Mock SoundCloud API response
        mock_response = [
            {
                'id': 123,
                'title': 'Test Playlist',
                'artwork_url': 'http://example.com/image.jpg',
                'track_count': 10,
                'permalink_url': 'http://soundcloud.com/playlist1'
            }
        ]
        mock_get_playlists.return_value = mock_response
        
        url = reverse('music:soundcloud-playlists')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)
        
    @patch('music.services.SoundCloudService.search_tracks')
    def test_search_soundcloud_tracks(self, mock_search):
        """Test searching for SoundCloud tracks"""
        # Mock SoundCloud API response
        mock_response = [
            {
                'id': 123,
                'title': 'Test Track',
                'user': {'username': 'Test Artist'},
                'artwork_url': 'http://example.com/track.jpg',
                'permalink_url': 'http://soundcloud.com/track1'
            }
        ]
        mock_search.return_value = mock_response
        
        url = reverse('music:soundcloud-search')
        response = self.client.get(url, {'q': 'test'})
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)

class MusicTrackViewSetTestCase(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Set up services
        self.spotify_service = MusicService.objects.create(
            user=self.user,
            service_type='spotify',
            access_token='spotify_token',
            refresh_token='spotify_refresh',
            expires_at=timezone.now() + timedelta(hours=1)
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
    
    @patch('music.utils.search_music')
    def test_search_tracks_across_services(self, mock_search):
        """Test searching for tracks across all services"""
        # Mock search results
        mock_response = {
            'spotify': [
                {
                    'id': 'track1',
                    'title': 'Test Track',
                    'artist': 'Test Artist',
                    'album': 'Test Album',
                    'album_art': 'http://example.com/album.jpg',
                    'url': 'http://spotify.com/track1',
                    'service': 'spotify'
                }
            ]
        }
        mock_search.return_value = mock_response
        
        url = reverse('music:tracks-search')
        response = self.client.get(url, {'q': 'test'})
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)
        
    @patch('music.utils.get_recently_played_tracks')
    def test_get_recently_played_tracks(self, mock_recent):
        """Test getting recently played tracks"""
        # Mock recently played results
        mock_response = {
            'spotify': [
                {
                    'id': 'track1',
                    'title': 'Test Track',
                    'artist': 'Test Artist',
                    'album': 'Test Album',
                    'album_art': 'http://example.com/album.jpg',
                    'url': 'http://spotify.com/track1',
                    'played_at': '2023-01-01T12:00:00Z',
                    'service': 'spotify'
                }
            ]
        }
        mock_recent.return_value = mock_response
        
        url = reverse('music:tracks-recently-played')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, mock_response)
