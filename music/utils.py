"""
Utility functions for music service integration
"""
from .models import MusicService
from .services import SpotifyService

def get_user_music_services(user):
    """
    Get all active music services for a user
    
    Returns a dict of service_type -> MusicService object
    """
    services = MusicService.objects.filter(user=user)
    return {service.service_type: service for service in services}

def search_music(user, query, service_type=None, limit=10):
    """
    Search for music across all connected services or a specific service
    
    Args:
        user: User object
        query: Search query string
        service_type: Optional service type to limit search to
        limit: Maximum results per service
        
    Returns:
        dict of service_type -> list of track results
    """
    results = {}
    services = get_user_music_services(user)
    
    if service_type and service_type in services:
        # Only search the specified service
        services = {service_type: services[service_type]}
    
    # Search Spotify
    if 'spotify' in services:
        spotify_results = SpotifyService.search_tracks(services['spotify'], query, limit)
        if 'error' not in spotify_results and 'tracks' in spotify_results:
            # Format the results
            results['spotify'] = [
                {
                    'id': track['id'],
                    'title': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'],
                    'album_art': track['album']['images'][0]['url'] if track['album']['images'] else None,
                    'url': track['external_urls']['spotify'],
                    'service': 'spotify'
                }
                for track in spotify_results['tracks']['items']
            ]
    
    # Apple Music and SoundCloud would be implemented similarly when added
    
    return results

def get_recently_played_tracks(user, service_type=None, limit=10):
    """
    Get recently played tracks from user's connected music services
    
    Args:
        user: User object
        service_type: Optional service type to limit results to
        limit: Maximum results per service
        
    Returns:
        dict of service_type -> list of track results
    """
    results = {}
    services = get_user_music_services(user)
    
    if service_type and service_type in services:
        # Only fetch from the specified service
        services = {service_type: services[service_type]}
    
    # Get Spotify recently played
    if 'spotify' in services:
        spotify_results = SpotifyService.get_recently_played(services['spotify'], limit)
        if 'error' not in spotify_results and 'items' in spotify_results:
            # Format the results
            results['spotify'] = [
                {
                    'id': item['track']['id'],
                    'title': item['track']['name'],
                    'artist': item['track']['artists'][0]['name'],
                    'album': item['track']['album']['name'],
                    'album_art': item['track']['album']['images'][0]['url'] if item['track']['album']['images'] else None,
                    'url': item['track']['external_urls']['spotify'],
                    'played_at': item['played_at'],
                    'service': 'spotify'
                }
                for item in spotify_results['items']
            ]
    
    # Apple Music and SoundCloud would be implemented similarly when added
    
    return results

def get_user_playlists(user, service_type=None, limit=20):
    """
    Get playlists from user's connected music services
    
    Args:
        user: User object
        service_type: Optional service type to limit results to
        limit: Maximum results per service
        
    Returns:
        dict of service_type -> list of playlist results
    """
    results = {}
    services = get_user_music_services(user)
    
    if service_type and service_type in services:
        # Only fetch from the specified service
        services = {service_type: services[service_type]}
    
    # Get Spotify playlists
    if 'spotify' in services:
        spotify_results = SpotifyService.get_user_playlists(services['spotify'], limit)
        if 'error' not in spotify_results and 'items' in spotify_results:
            # Format the results
            results['spotify'] = [
                {
                    'id': playlist['id'],
                    'name': playlist['name'],
                    'image': playlist['images'][0]['url'] if playlist['images'] else None,
                    'track_count': playlist['tracks']['total'],
                    'url': playlist['external_urls']['spotify'],
                    'service': 'spotify'
                }
                for playlist in spotify_results['items']
            ]
    
    # Apple Music and SoundCloud would be implemented similarly when added
    
    return results

def get_playlist_tracks(user, playlist_id, service_type, limit=50):
    """
    Get tracks from a specific playlist
    
    Args:
        user: User object
        playlist_id: ID of playlist to fetch tracks from
        service_type: Service type (spotify, apple, etc.)
        limit: Maximum number of tracks to return
        
    Returns:
        list of track results or None if error
    """
    services = get_user_music_services(user)
    
    if service_type not in services:
        return None
    
    # Get Spotify playlist tracks
    if service_type == 'spotify':
        spotify_results = SpotifyService.get_playlist_tracks(services['spotify'], playlist_id, limit)
        if 'error' not in spotify_results and 'items' in spotify_results:
            # Format the results
            return [
                {
                    'id': item['track']['id'],
                    'title': item['track']['name'],
                    'artist': item['track']['artists'][0]['name'],
                    'album': item['track']['album']['name'],
                    'album_art': item['track']['album']['images'][0]['url'] if item['track']['album']['images'] else None,
                    'url': item['track']['external_urls']['spotify'],
                    'service': 'spotify'
                }
                for item in spotify_results['items'] if item['track'] is not None
            ]
    
    # Apple Music and SoundCloud would be implemented similarly when added
    
    return None

def get_track_details(user, track_id, service_type):
    """
    Get detailed information about a specific track
    
    Args:
        user: User object
        track_id: ID of track to get details for
        service_type: Service type (spotify, apple, etc.)
        
    Returns:
        dict with track details or None if error
    """
    services = get_user_music_services(user)
    
    if service_type not in services:
        return None
    
    # Get Spotify track details
    if service_type == 'spotify':
        spotify_results = SpotifyService.get_track(services['spotify'], track_id)
        if 'error' not in spotify_results:
            # Format the result
            return {
                'id': spotify_results['id'],
                'title': spotify_results['name'],
                'artist': spotify_results['artists'][0]['name'],
                'album': spotify_results['album']['name'],
                'album_art': spotify_results['album']['images'][0]['url'] if spotify_results['album']['images'] else None,
                'url': spotify_results['external_urls']['spotify'],
                'preview_url': spotify_results['preview_url'],
                'duration_ms': spotify_results['duration_ms'],
                'service': 'spotify'
            }
    
    # Apple Music and SoundCloud would be implemented similarly when added
    
    return None 