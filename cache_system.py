"""
Core caching system for BOPMaps backend.

This module implements a multi-level caching strategy for map data including:
- Redis-based caching for high-performance access
- Spatial grid-based caching for geographic data
- Automatic cache invalidation strategies
- Cache statistics and monitoring
"""

import json
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from django.core.cache import cache
from django.conf import settings
from django.contrib.gis.geos import Point, Polygon
from redis import Redis
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('bopmaps.cache')

# Initialize Redis connection if available
try:
    redis_client = Redis.from_url(
        settings.CACHES['default']['LOCATION'] 
        if 'redis' in settings.CACHES['default']['LOCATION'] 
        else None
    )
    REDIS_AVAILABLE = True
except (AttributeError, ImportError, ConnectionError):
    REDIS_AVAILABLE = False
    redis_client = None
    logger.warning("Redis not available, falling back to framework cache")

# Cache timeout settings (in seconds)
CACHE_TIMEOUTS = {
    'tile': 60 * 60 * 24 * 7,  # 7 days for map tiles
    'vector_data': 60 * 60 * 24,  # 1 day for vector data
    'pins': 60 * 15,  # 15 minutes for pins data
    'settings': 60 * 60 * 24 * 30,  # 30 days for user settings
    'trending': 60 * 30,  # 30 minutes for trending data
}


class SpatialCache:
    """
    Implements spatial caching strategies for geographic data.
    """
    
    @staticmethod
    def get_grid_cell(lat: float, lng: float, precision: int = 2) -> Tuple[float, float]:
        """
        Get grid cell coordinates for a given latitude and longitude.
        
        Args:
            lat: Latitude
            lng: Longitude
            precision: Number of decimal places for grid precision
            
        Returns:
            Tuple of grid cell coordinates (lat_grid, lng_grid)
        """
        factor = 10 ** precision
        return (int(float(lat) * factor) / factor, 
                int(float(lng) * factor) / factor)
    
    @staticmethod
    def get_cache_key(prefix: str, lat: float, lng: float, zoom: int = None, 
                       additional_params: Dict = None, precision: int = 2) -> str:
        """
        Generate a cache key for spatial data.
        
        Args:
            prefix: Key prefix (e.g., 'pins', 'buildings')
            lat: Latitude
            lng: Longitude
            zoom: Zoom level (optional)
            additional_params: Additional parameters to include in the key
            precision: Grid precision
            
        Returns:
            Cache key string
        """
        lat_grid, lng_grid = SpatialCache.get_grid_cell(lat, lng, precision)
        
        # Start with base key
        key_parts = [prefix, f"grid:{lat_grid}:{lng_grid}"]
        
        # Add zoom if provided
        if zoom is not None:
            key_parts.append(f"zoom:{zoom}")
            
        # Add additional params
        if additional_params:
            for k, v in sorted(additional_params.items()):
                key_parts.append(f"{k}:{v}")
                
        # Join all parts with colons
        return ":".join(key_parts)
    
    @staticmethod
    def find_related_keys(prefix: str, lat: float, lng: float, precision: int = 2) -> List[str]:
        """
        Find cache keys related to a specific location.
        
        Args:
            prefix: Key prefix
            lat: Latitude
            lng: Longitude
            precision: Grid precision
            
        Returns:
            List of related cache keys
        """
        lat_grid, lng_grid = SpatialCache.get_grid_cell(lat, lng, precision)
        
        # This pattern will match keys for this grid cell
        pattern = f"{prefix}:grid:{lat_grid}:{lng_grid}:*"
        
        if REDIS_AVAILABLE:
            # Use Redis to find matching keys
            return [key.decode('utf-8') for key in redis_client.keys(pattern)]
        else:
            # Without Redis, we can't easily search for keys
            # This is a limitation when using the default cache backend
            logger.warning("Cannot find related keys without Redis")
            return []
    
    @staticmethod
    def invalidate_area(prefix: str, bounds: Polygon, precision: int = 2) -> int:
        """
        Invalidate cache for an entire area.
        
        Args:
            prefix: Key prefix
            bounds: Polygon defining the area
            precision: Grid precision
            
        Returns:
            Number of invalidated cache keys
        """
        if not REDIS_AVAILABLE:
            logger.warning("Cannot invalidate area without Redis")
            return 0
            
        # Get bounding box
        minx, miny, maxx, maxy = bounds.extent
        
        # Generate all grid cells within this bounding box
        factor = 10 ** precision
        
        min_lat_grid = int(miny * factor) / factor
        max_lat_grid = int(maxy * factor) / factor
        min_lng_grid = int(minx * factor) / factor
        max_lng_grid = int(maxx * factor) / factor
        
        # Generate patterns for all cells
        patterns = []
        
        # Iterate through all grid cells in the bounding box
        lat_grid = min_lat_grid
        while lat_grid <= max_lat_grid:
            lng_grid = min_lng_grid
            while lng_grid <= max_lng_grid:
                pattern = f"{prefix}:grid:{lat_grid}:{lng_grid}:*"
                patterns.append(pattern)
                lng_grid = (int(lng_grid * factor) + 1) / factor
                
            lat_grid = (int(lat_grid * factor) + 1) / factor
            
        # Delete all matching keys
        count = 0
        for pattern in patterns:
            keys = redis_client.keys(pattern)
            if keys:
                count += len(keys)
                for key in keys:
                    redis_client.delete(key)
                    
        return count


class MapCache:
    """
    Main caching interface for map data.
    """
    
    @staticmethod
    def get_tile(z: int, x: int, y: int) -> Optional[bytes]:
        """
        Get a map tile from cache.
        
        Args:
            z: Zoom level
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Tile data as bytes or None if not in cache
        """
        cache_key = f"osm_tile:{z}:{x}:{y}"
        return cache.get(cache_key)
    
    @staticmethod
    def set_tile(z: int, x: int, y: int, data: bytes) -> None:
        """
        Store a map tile in cache.
        
        Args:
            z: Zoom level
            x: X coordinate
            y: Y coordinate
            data: Tile image data
        """
        cache_key = f"osm_tile:{z}:{x}:{y}"
        cache.set(cache_key, data, timeout=CACHE_TIMEOUTS['tile'])
    
    @staticmethod
    def get_tile_metadata(cache_key: str, metadata_key: str) -> Optional[str]:
        """
        Get metadata for a tile (like ETags).
        
        Args:
            cache_key: The tile cache key
            metadata_key: The specific metadata key to retrieve
            
        Returns:
            Metadata value or None if not in cache
        """
        # Extract z, x, y from the cache_key if it's in the format "tile_z_x_y"
        parts = cache_key.split("_")
        if len(parts) == 4 and parts[0] == "tile":
            try:
                z, x, y = int(parts[1]), int(parts[2]), int(parts[3])
                metadata_cache_key = f"osm_tile:{z}:{x}:{y}:metadata:{metadata_key}"
                return cache.get(metadata_cache_key)
            except ValueError:
                pass
        
        # Fallback to the original format
        metadata_cache_key = f"{cache_key}:metadata:{metadata_key}"
        return cache.get(metadata_cache_key)
    
    @staticmethod
    def set_tile_metadata(cache_key: str, metadata_key: str, value: str) -> None:
        """
        Store metadata for a tile (like ETags).
        
        Args:
            cache_key: The tile cache key
            metadata_key: The specific metadata key to store
            value: The metadata value to store
        """
        # Extract z, x, y from the cache_key if it's in the format "tile_z_x_y"
        parts = cache_key.split("_")
        if len(parts) == 4 and parts[0] == "tile":
            try:
                z, x, y = int(parts[1]), int(parts[2]), int(parts[3])
                metadata_cache_key = f"osm_tile:{z}:{x}:{y}:metadata:{metadata_key}"
                cache.set(metadata_cache_key, value, timeout=CACHE_TIMEOUTS['tile'])
                return
            except ValueError:
                pass
        
        # Fallback to the original format
        metadata_cache_key = f"{cache_key}:metadata:{metadata_key}"
        cache.set(metadata_cache_key, value, timeout=CACHE_TIMEOUTS['tile'])
        
    @staticmethod
    def get_vector_data(data_type: str, lat: float, lng: float, zoom: int,
                        radius: int = 1000, additional_params: Dict = None) -> Optional[Dict]:
        """
        Get vector data from cache.
        
        Args:
            data_type: Type of vector data (buildings, roads, etc.)
            lat: Center latitude
            lng: Center longitude
            zoom: Zoom level
            radius: Search radius in meters
            additional_params: Additional parameters
            
        Returns:
            Vector data or None if not in cache
        """
        params = additional_params or {}
        params['radius'] = radius
        
        cache_key = SpatialCache.get_cache_key(
            prefix=f"vector:{data_type}",
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=params
        )
        
        return cache.get(cache_key)
    
    @staticmethod
    def set_vector_data(data_type: str, lat: float, lng: float, zoom: int,
                       data: Dict, radius: int = 1000, 
                       additional_params: Dict = None) -> None:
        """
        Store vector data in cache.
        
        Args:
            data_type: Type of vector data (buildings, roads, etc.)
            lat: Center latitude
            lng: Center longitude
            zoom: Zoom level
            data: Vector data to cache
            radius: Search radius in meters
            additional_params: Additional parameters
        """
        params = additional_params or {}
        params['radius'] = radius
        
        cache_key = SpatialCache.get_cache_key(
            prefix=f"vector:{data_type}",
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=params
        )
        
        cache.set(cache_key, data, timeout=CACHE_TIMEOUTS['vector_data'])
    
    @staticmethod
    def get_pins(lat: float, lng: float, zoom: int, radius: int = 1000, 
                user_id: int = None) -> Optional[Dict]:
        """
        Get pins data from cache.
        
        Args:
            lat: Center latitude
            lng: Center longitude
            zoom: Zoom level
            radius: Search radius in meters
            user_id: User ID for personalized pins
            
        Returns:
            Pins data or None if not in cache
        """
        params = {'radius': radius}
        if user_id:
            params['user'] = user_id
            
        cache_key = SpatialCache.get_cache_key(
            prefix="pins",
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=params
        )
        
        return cache.get(cache_key)
    
    @staticmethod
    def set_pins(lat: float, lng: float, zoom: int, data: Dict, 
                radius: int = 1000, user_id: int = None) -> None:
        """
        Store pins data in cache.
        
        Args:
            lat: Center latitude
            lng: Center longitude
            zoom: Zoom level
            data: Pins data to cache
            radius: Search radius in meters
            user_id: User ID for personalized pins
        """
        params = {'radius': radius}
        if user_id:
            params['user'] = user_id
            
        cache_key = SpatialCache.get_cache_key(
            prefix="pins",
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=params
        )
        
        cache.set(cache_key, data, timeout=CACHE_TIMEOUTS['pins'])
    
    @staticmethod
    def invalidate_pins_near(lat: float, lng: float, radius: int = 1000) -> None:
        """
        Invalidate pins cache near a specific location.
        
        Args:
            lat: Center latitude
            lng: Center longitude
            radius: Radius to invalidate in meters
        """
        # Create a buffer around the point
        point = Point(lng, lat, srid=4326)
        bounds = point.buffer(radius / 111000).envelope  # Approximate conversion from meters
        
        # Invalidate all pins in this area
        count = SpatialCache.invalidate_area("pins", bounds)
        logger.info(f"Invalidated {count} pins cache entries near {lat}, {lng}")
        
    @staticmethod
    def get_user_settings(user_id: int) -> Optional[Dict]:
        """
        Get user map settings from cache.
        
        Args:
            user_id: User ID
            
        Returns:
            User settings or None if not in cache
        """
        cache_key = f"user_settings:{user_id}"
        return cache.get(cache_key)
    
    @staticmethod
    def set_user_settings(user_id: int, settings: Dict) -> None:
        """
        Store user map settings in cache.
        
        Args:
            user_id: User ID
            settings: Settings data to cache
        """
        cache_key = f"user_settings:{user_id}"
        cache.set(cache_key, settings, timeout=CACHE_TIMEOUTS['settings'])
        
    @staticmethod
    def invalidate_user_settings(user_id: int) -> None:
        """
        Invalidate user settings cache.
        
        Args:
            user_id: User ID
        """
        cache_key = f"user_settings:{user_id}"
        cache.delete(cache_key)
        
    @staticmethod
    def get_cache_stats() -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary of cache statistics
        """
        if REDIS_AVAILABLE:
            info = redis_client.info()
            return {
                'redis_version': info.get('redis_version'),
                'used_memory_human': info.get('used_memory_human'),
                'hit_rate': info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1) + 0.001),
                'total_keys': sum(db.get('keys', 0) for db_name, db in info.items() if db_name.startswith('db')),
                'tile_keys': len(redis_client.keys("osm_tile:*")),
                'vector_keys': len(redis_client.keys("vector:*")),
                'pins_keys': len(redis_client.keys("pins:*")),
                'settings_keys': len(redis_client.keys("user_settings:*")),
            }
        else:
            return {
                'status': 'Redis not available',
                'using': 'Django default cache backend'
            } 