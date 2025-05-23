"""
Middleware for optimizing map-related requests and caching
"""

import time
import logging
import re
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.core.cache import caches, cache
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
        Process the request before the view (and other middleware) are called
        
        Args:
            request: The HTTP request
            
        Returns:
            HttpResponse if the request is handled or None to continue processing
        """
        # Only handle GET requests to tile URLs
        if not (hasattr(request, 'method') and request.method == 'GET'):
            return None
            
        match = self.TILE_URL_PATTERN.match(request.path) if hasattr(request, 'path') else None
        if not match:
            return None
            
        # Extract tile coordinates
        z, x, y = map(int, match.groups())
        
        # Check if we should throttle this request
        client_ip = self._get_client_ip(request)
        now = time.time()
        
        # Clean up old requests
        self.request_counts = {ip: [t for t in times if t > now - 60] 
                              for ip, times in self.request_counts.items()}
        
        # Check if rate limit exceeded
        if (client_ip in self.request_counts and 
            len(self.request_counts[client_ip]) >= self.MAX_REQUESTS_PER_MINUTE):
            logger.warning('Rate limit exceeded for client %s', client_ip)
            return HttpResponse('Rate limit exceeded', status=429,
                              headers={'Retry-After': '60'})
                              
        # Add this request to the count
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []
        self.request_counts[client_ip].append(now)
        
        # Try to get from cache
        cached_tile = MapCache.get_tile(z, x, y)
        if not cached_tile:
            # Let the view handle fetching the tile
            return None
            
        # Handle conditional requests with If-None-Match
        etag_key = f"osm_tile:{z}:{x}:{y}:metadata:etag"
        cached_etag = cache.get(etag_key)
        
        if cached_etag and 'HTTP_IF_NONE_MATCH' in request.META:
            client_etag = request.META['HTTP_IF_NONE_MATCH']
            # Normalize ETags by removing quotes for comparison
            client_etag_clean = client_etag.replace('"', '')
            cached_etag_clean = cached_etag.replace('"', '')
            
            if client_etag_clean == cached_etag_clean:
                response = HttpResponse(status=304)
                self._add_cache_headers(response, 60*60*24*7)
                response['ETag'] = cached_etag
                return response
        
        # Serve from cache
        response = HttpResponse(cached_tile, content_type='image/png')
        self._add_cache_headers(response, 60*60*24*7)  # 7 days
        if cached_etag:
            response['ETag'] = cached_etag
        
        return response
        
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
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('bopmaps.geo.vector')
        
    def __call__(self, request):
        # Only process vector data endpoints
        if '/api/geo/buildings/' in request.path:
            self.logger.info(
                'Vector data request received - Path: %s, Method: %s, User: %s',
                request.path,
                request.method,
                request.user.username if request.user.is_authenticated else 'Anonymous'
            )
            
            # Log query parameters
            if request.GET:
                self.logger.debug('Vector request parameters: %s', dict(request.GET))

        response = self.get_response(request)

        # Log response details for vector data endpoints
        if '/api/geo/buildings/' in request.path:
            self.logger.info(
                'Vector data response sent - Status: %d, Size: %d bytes',
                response.status_code,
                len(response.content) if hasattr(response, 'content') else 0
            )

            # Log cache status if present in response headers
            cache_status = response.headers.get('X-Cache-Status')
            if cache_status:
                self.logger.info('Cache status for vector request: %s', cache_status)

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Log view information for vector data endpoints
        if '/api/geo/buildings/' in request.path:
            self.logger.debug(
                'Processing vector data view - View: %s, Args: %s, Kwargs: %s',
                view_func.__name__ if hasattr(view_func, '__name__') else 'Unknown',
                view_args,
                view_kwargs
            )
        return None

    def process_exception(self, request, exception):
        # Log any exceptions in vector data processing
        if '/api/geo/buildings/' in request.path:
            self.logger.error(
                'Error processing vector data request - Path: %s, Error: %s',
                request.path,
                str(exception),
                exc_info=True
            )
        return None
        
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