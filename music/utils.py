"""
Utility functions for music service integration
"""
from .models import MusicService
from .services import SpotifyService, AppleMusicService, SoundCloudService
import logging

logger = logging.getLogger('bopmaps')

def get_user_music_services(user):
    """
    Get all active music services for a user
    
    Returns a dict of service_type -> MusicService object
    """
    services = MusicService.objects.filter(user=user)
    return {service.service_type: service for service in services}

def get_service_class(service_type):
    """
    Get the appropriate service class based on service type
    """
    if service_type == 'spotify':
        return SpotifyService
    elif service_type == 'apple':
        return AppleMusicService
    elif service_type == 'soundcloud':
        return SoundCloudService
    else:
        raise ValueError(f"Unsupported service type: {service_type}")

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
    
    # Search each connected service
    for service_type, music_service in services.items():
        try:
            service_class = get_service_class(service_type)
            service_results = service_class.search_tracks(music_service, query, limit)
            
            # Format results based on service type
            if service_type == 'spotify' and 'error' not in service_results and 'tracks' in service_results:
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
                    for track in service_results['tracks']['items']
                ]
            
            elif service_type == 'apple' and 'error' not in service_results and 'results' in service_results:
                if 'songs' in service_results['results']:
                    results['apple'] = [
                        {
                            'id': track['id'],
                            'title': track['attributes']['name'],
                            'artist': track['attributes']['artistName'],
                            'album': track['attributes']['albumName'],
                            'album_art': track['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300'),
                            'url': track['attributes'].get('url', ''),
                            'service': 'apple'
                        }
                        for track in service_results['results']['songs']['data']
                    ]
            
            elif service_type == 'soundcloud' and 'error' not in service_results:
                results['soundcloud'] = [
                    {
                        'id': str(track['id']),
                        'title': track['title'],
                        'artist': track['user']['username'],
                        'album': track.get('release_title', ''),
                        'album_art': track['artwork_url'].replace('-large', '-t500x500') if track.get('artwork_url') else None,
                        'url': track['permalink_url'],
                        'service': 'soundcloud'
                    }
                    for track in service_results
                ]
        except Exception as e:
            logger.error(f"Error searching {service_type}: {str(e)}")
    
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
    
    # Get recently played from each connected service
    for service_type, music_service in services.items():
        try:
            service_class = get_service_class(service_type)
            service_results = service_class.get_recently_played(music_service, limit)
            
            # Format results based on service type
            if service_type == 'spotify' and 'error' not in service_results and 'items' in service_results:
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
                    for item in service_results['items']
                ]
            
            elif service_type == 'apple' and 'error' not in service_results and 'data' in service_results:
                results['apple'] = [
                    {
                        'id': item['id'],
                        'title': item['attributes']['name'],
                        'artist': item['attributes']['artistName'],
                        'album': item['attributes']['albumName'],
                        'album_art': item['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300'),
                        'url': item['attributes'].get('url', ''),
                        'played_at': item['attributes'].get('lastPlayedDate', ''),
                        'service': 'apple'
                    }
                    for item in service_results['data']
                ]
            
            elif service_type == 'soundcloud' and 'error' not in service_results and 'collection' in service_results:
                results['soundcloud'] = [
                    {
                        'id': str(item['track']['id']),
                        'title': item['track']['title'],
                        'artist': item['track']['user']['username'],
                        'album': item['track'].get('release_title', ''),
                        'album_art': item['track'].get('artwork_url', '').replace('-large', '-t500x500') if item['track'].get('artwork_url') else None,
                        'url': item['track']['permalink_url'],
                        'played_at': item.get('played_at', ''),
                        'service': 'soundcloud'
                    }
                    for item in service_results['collection']
                ]
        except Exception as e:
            logger.error(f"Error getting recently played for {service_type}: {str(e)}")
    
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
    
    # Get playlists from each connected service
    for service_type, music_service in services.items():
        try:
            service_class = get_service_class(service_type)
            service_results = service_class.get_user_playlists(music_service, limit)
            
            # Format results based on service type
            if service_type == 'spotify' and 'error' not in service_results and 'items' in service_results:
                results['spotify'] = [
                    {
                        'id': playlist['id'],
                        'name': playlist['name'],
                        'image': playlist['images'][0]['url'] if playlist['images'] else None,
                        'track_count': playlist['tracks']['total'],
                        'url': playlist['external_urls']['spotify'],
                        'service': 'spotify'
                    }
                    for playlist in service_results['items']
                ]
            
            elif service_type == 'apple' and 'error' not in service_results and 'data' in service_results:
                results['apple'] = [
                    {
                        'id': playlist['id'],
                        'name': playlist['attributes']['name'],
                        'image': playlist['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300') if 'artwork' in playlist['attributes'] else None,
                        'track_count': playlist['attributes'].get('trackCount', 0),
                        'url': playlist['attributes'].get('url', ''),
                        'service': 'apple'
                    }
                    for playlist in service_results['data']
                ]
            
            elif service_type == 'soundcloud' and 'error' not in service_results:
                results['soundcloud'] = [
                    {
                        'id': str(playlist['id']),
                        'name': playlist['title'],
                        'image': playlist.get('artwork_url', '').replace('-large', '-t500x500') if playlist.get('artwork_url') else None,
                        'track_count': playlist.get('track_count', 0),
                        'url': playlist['permalink_url'],
                        'service': 'soundcloud'
                    }
                    for playlist in service_results
                ]
        except Exception as e:
            logger.error(f"Error getting playlists for {service_type}: {str(e)}")
    
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
    
    music_service = services[service_type]
    
    try:
        service_class = get_service_class(service_type)
        service_results = service_class.get_playlist_tracks(music_service, playlist_id, limit)
        
        # Format results based on service type
        if service_type == 'spotify' and 'error' not in service_results and 'items' in service_results:
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
                for item in service_results['items'] if item['track'] is not None
            ]
        
        elif service_type == 'apple' and 'error' not in service_results and 'data' in service_results:
            return [
                {
                    'id': track['id'],
                    'title': track['attributes']['name'],
                    'artist': track['attributes']['artistName'],
                    'album': track['attributes']['albumName'],
                    'album_art': track['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300'),
                    'url': track['attributes'].get('url', ''),
                    'service': 'apple'
                }
                for track in service_results['data']
            ]
        
        elif service_type == 'soundcloud' and 'error' not in service_results and 'items' in service_results:
            return [
                {
                    'id': str(track['id']),
                    'title': track['title'],
                    'artist': track['user']['username'],
                    'album': track.get('release_title', ''),
                    'album_art': track.get('artwork_url', '').replace('-large', '-t500x500') if track.get('artwork_url') else None,
                    'url': track['permalink_url'],
                    'service': 'soundcloud'
                }
                for track in service_results['items']
            ]
    except Exception as e:
        logger.error(f"Error getting playlist tracks for {service_type}: {str(e)}")
    
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
    
    music_service = services[service_type]
    
    try:
        service_class = get_service_class(service_type)
        service_results = service_class.get_track(music_service, track_id)
        
        # Format results based on service type
        if service_type == 'spotify' and 'error' not in service_results:
            return {
                'id': service_results['id'],
                'title': service_results['name'],
                'artist': service_results['artists'][0]['name'],
                'album': service_results['album']['name'],
                'album_art': service_results['album']['images'][0]['url'] if service_results['album']['images'] else None,
                'url': service_results['external_urls']['spotify'],
                'preview_url': service_results['preview_url'],
                'duration_ms': service_results['duration_ms'],
                'service': 'spotify'
            }
        
        elif service_type == 'apple' and 'error' not in service_results and 'data' in service_results:
            track = service_results['data'][0]  # Apple Music returns an array
            return {
                'id': track['id'],
                'title': track['attributes']['name'],
                'artist': track['attributes']['artistName'],
                'album': track['attributes']['albumName'],
                'album_art': track['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300'),
                'url': track['attributes'].get('url', ''),
                'preview_url': track['attributes'].get('previews', [{}])[0].get('url', None),
                'duration_ms': track['attributes'].get('durationInMillis', 0),
                'service': 'apple'
            }
        
        elif service_type == 'soundcloud' and 'error' not in service_results:
            return {
                'id': str(service_results['id']),
                'title': service_results['title'],
                'artist': service_results['user']['username'],
                'album': service_results.get('release_title', ''),
                'album_art': service_results.get('artwork_url', '').replace('-large', '-t500x500') if service_results.get('artwork_url') else None,
                'url': service_results['permalink_url'],
                'preview_url': service_results.get('stream_url', None),
                'duration_ms': service_results.get('duration', 0),
                'service': 'soundcloud'
            }
    except Exception as e:
        logger.error(f"Error getting track details for {service_type}: {str(e)}")
    
    return None

def get_saved_tracks(user, service_type=None, limit=50, offset=0):
    """
    Get saved/liked tracks from user's connected music services
    
    Args:
        user: User object
        service_type: Optional service type to limit results to
        limit: Maximum results per service
        offset: Number of results to skip
        
    Returns:
        dict of service_type -> list of track results
    """
    results = {}
    services = get_user_music_services(user)
    
    if service_type and service_type in services:
        # Only fetch from the specified service
        services = {service_type: services[service_type]}
    
    # Get saved tracks from each connected service
    for service_type, music_service in services.items():
        try:
            service_class = get_service_class(service_type)
            service_results = service_class.get_saved_tracks(music_service, limit, offset)
            
            # Format results based on service type
            if service_type == 'spotify' and 'error' not in service_results and 'items' in service_results:
                results['spotify'] = [
                    {
                        'id': item['track']['id'],
                        'title': item['track']['name'],
                        'artist': item['track']['artists'][0]['name'],
                        'album': item['track']['album']['name'],
                        'album_art': item['track']['album']['images'][0]['url'] if item['track']['album']['images'] else None,
                        'url': item['track']['external_urls']['spotify'],
                        'added_at': item['added_at'],
                        'service': 'spotify'
                    }
                    for item in service_results['items']
                ]
            
            elif service_type == 'apple' and 'error' not in service_results and 'data' in service_results:
                results['apple'] = [
                    {
                        'id': track['id'],
                        'title': track['attributes']['name'],
                        'artist': track['attributes']['artistName'],
                        'album': track['attributes']['albumName'],
                        'album_art': track['attributes']['artwork']['url'].replace('{w}', '300').replace('{h}', '300'),
                        'url': track['attributes'].get('url', ''),
                        'added_at': track['attributes'].get('dateAdded', ''),
                        'service': 'apple'
                    }
                    for track in service_results['data']
                ]
            
            elif service_type == 'soundcloud' and 'error' not in service_results:
                results['soundcloud'] = [
                    {
                        'id': str(track['id']),
                        'title': track['title'],
                        'artist': track['user']['username'],
                        'album': track.get('release_title', ''),
                        'album_art': track.get('artwork_url', '').replace('-large', '-t500x500') if track.get('artwork_url') else None,
                        'url': track['permalink_url'],
                        'added_at': track.get('created_at', ''),
                        'service': 'soundcloud'
                    }
                    for track in service_results
                ]
        except Exception as e:
            logger.error(f"Error getting saved tracks for {service_type}: {str(e)}")
    
    return results 