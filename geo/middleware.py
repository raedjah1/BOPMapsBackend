"""
Middleware for optimizing map-related requests and caching
"""

import time
import logging
import re
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse
from cache_system import MapCache

logger = logging.getLogger('bopmaps.cache')

class MapTileOptimizationMiddleware(MiddlewareMixin):
    """
    Middleware for optimizing and caching map tile requests
    
    This middleware:
    1. Handles caching for OSM tile requests
    2. Adds appropriate headers for client-side caching
    3. Throttles requests to external tile servers
    4. Tracks tile usage statistics
    """
    
    # Pattern to match tile URLs
    TILE_URL_PATTERN = re.compile(r'^/api/geo/tiles/osm/(\d+)/(\d+)/(\d+)\.png$')
    
    # Rate limiting settings
    MAX_REQUESTS_PER_MINUTE = 100
    
    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.tile_cache = caches['tiles'] if 'tiles' in settings.CACHES else caches['default']
        self.request_counts = {}
        
    def process_request(self, request):
        """
        Process the request before it reaches the view
        
        Args:
            request: The HTTP request
            
        Returns:
            HttpResponse if we can serve from cache, otherwise None
        """
        # Only process GET requests to tile URLs
        if request.method != 'GET':
            return None
            
        match = self.TILE_URL_PATTERN.match(request.path)
        if not match:
            return None
            
        # Extract tile coordinates
        z, x, y = map(int, match.groups())
        
        # Check if we need to throttle
        client_ip = self._get_client_ip(request)
        if self._should_throttle(client_ip):
            logger.warning(f"Throttling tile requests from {client_ip}")
            return HttpResponse("Rate limit exceeded", status=429)
            
        # Try to get from cache
        cached_tile = MapCache.get_tile(z, x, y)
        if cached_tile:
            # Serve from cache with appropriate headers
            response = HttpResponse(cached_tile, content_type="image/png")
            self._add_cache_headers(response, 60*60*24*7)  # 7 days
            return response
            
        # Let the view handle it
        return None
        
    def process_response(self, request, response):
        """
        Process the response after the view has handled it
        
        Args:
            request: The HTTP request
            response: The HTTP response
            
        Returns:
            The processed HTTP response
        """
        # Add cache headers to tile responses
        match = self.TILE_URL_PATTERN.match(request.path) if hasattr(request, 'path') else None
        
        if match and response.status_code == 200:
            # Cache successful tile responses
            z, x, y = map(int, match.groups())
            
            # Add cache headers
            self._add_cache_headers(response, 60*60*24*7)  # 7 days
            
            # Store in cache if not already there
            if not MapCache.get_tile(z, x, y):
                MapCache.set_tile(z, x, y, response.content)
                
        return response
        
    def _get_client_ip(self, request):
        """
        Get the client IP address from the request
        
        Args:
            request: The HTTP request
            
        Returns:
            Client IP address as a string
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', 'unknown')
        return ip
        
    def _should_throttle(self, client_ip):
        """
        Check if requests from this IP should be throttled
        
        Args:
            client_ip: Client IP address
            
        Returns:
            True if requests should be throttled, False otherwise
        """
        now = int(time.time() / 60)  # Current minute
        
        # Clean up old entries
        self.request_counts = {k: v for k, v in self.request_counts.items() if k[1] == now}
        
        # Check and update request count
        key = (client_ip, now)
        count = self.request_counts.get(key, 0)
        
        if count >= self.MAX_REQUESTS_PER_MINUTE:
            return True
            
        self.request_counts[key] = count + 1
        return False
        
    def _add_cache_headers(self, response, max_age):
        """
        Add appropriate cache headers to the response
        
        Args:
            response: The HTTP response
            max_age: Maximum age in seconds
            
        Returns:
            None (modifies response in place)
        """
        response['Cache-Control'] = f'public, max-age={max_age}'
        response['Expires'] = time.strftime(
            "%a, %d %b %Y %H:%M:%S GMT", 
            time.gmtime(time.time() + max_age)
        )
        
        
class VectorDataOptimizationMiddleware(MiddlewareMixin):
    """
    Middleware for optimizing vector data requests
    
    This middleware:
    1. Adds appropriate ETags for vector data
    2. Implements conditional GET for vector data
    3. Adds compression for vector data responses
    """
    
    # Pattern to match vector data URLs
    VECTOR_URL_PATTERN = re.compile(r'^/api/geo/(buildings|roads|parks)/$')
    
    def process_request(self, request):
        """
        Process the request before it reaches the view
        
        Args:
            request: The HTTP request
            
        Returns:
            HttpResponse if we can serve from cached ETag, otherwise None
        """
        # Only process GET requests to vector data URLs
        if request.method != 'GET':
            return None
            
        match = self.VECTOR_URL_PATTERN.match(request.path)
        if not match:
            return None
            
        # Get the data type
        data_type = match.group(1)
        
        # Get query parameters
        lat = request.GET.get('latitude') or (
            (float(request.GET.get('north', 0)) + float(request.GET.get('south', 0))) / 2
        )
        lng = request.GET.get('longitude') or (
            (float(request.GET.get('east', 0)) + float(request.GET.get('west', 0))) / 2
        )
        zoom = int(request.GET.get('zoom', 16))
        
        # Create additional params for cache key
        additional_params = {}
        for param in ['north', 'south', 'east', 'west', 'radius']:
            if param in request.GET:
                additional_params[param] = request.GET[param]
                
        # Try to get from cache
        cached_data = MapCache.get_vector_data(
            data_type=data_type,
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=additional_params
        )
        
        if cached_data:
            # Generate ETag
            etag = f'W/"{hash(str(cached_data))}"'
            
            # Check If-None-Match header
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
            if if_none_match and if_none_match == etag:
                # Return 304 Not Modified
                response = HttpResponse(status=304)
                response['ETag'] = etag
                return response
                
        # Let the view handle it
        return None
        
    def process_response(self, request, response):
        """
        Process the response after the view has handled it
        
        Args:
            request: The HTTP request
            response: The HTTP response
            
        Returns:
            The processed HTTP response
        """
        # Only process successful responses to vector data URLs
        if not hasattr(request, 'path') or response.status_code != 200:
            return response
            
        match = self.VECTOR_URL_PATTERN.match(request.path)
        if not match:
            return response
            
        # Generate ETag
        etag = f'W/"{hash(response.content)}"'
        response['ETag'] = etag
        
        # Add cache headers
        response['Cache-Control'] = 'private, max-age=3600'  # 1 hour
        
        return response 