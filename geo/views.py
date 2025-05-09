from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.gzip import gzip_page
from django.core.exceptions import ValidationError

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import TrendingArea, UserLocation, Building, Road, Park, CachedRegion, UserMapSettings
from .serializers import (TrendingAreaSerializer, UserLocationSerializer, 
                         BuildingSerializer, RoadSerializer, ParkSerializer,
                         CachedRegionSerializer, UserMapSettingsSerializer)

import logging
import requests
import sys
from io import BytesIO
from cache_system import MapCache, CACHE_TIMEOUTS
from django.core.cache import cache

logger = logging.getLogger('bopmaps')

class TrendingAreaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for trending areas (read-only)
    """
    queryset = TrendingArea.objects.all()
    serializer_class = TrendingAreaSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by distance if coordinates provided
        lat = self.request.query_params.get('latitude')
        lng = self.request.query_params.get('longitude')
        radius = self.request.query_params.get('radius', 5000)
        
        if lat and lng:
            try:
                user_location = Point(float(lng), float(lat))
                radius_m = int(radius)
                
                queryset = queryset.annotate(
                    distance=Distance('center', user_location)
                ).filter(
                    distance__lte=D(m=radius_m)
                ).order_by('distance')
                
            except (ValueError, TypeError):
                logger.error(f"Invalid coordinates in TrendingAreaViewSet: {lat}, {lng}")
                
        # Order by pin count (most popular first)
        return queryset.order_by('-pin_count')
    
    @action(detail=False, methods=['get'])
    def map_visualization(self, request):
        """
        Get trending areas with visualization parameters for heatmap
        """
        # Try to get from cache first
        cache_key = "trending_heatmap_data"
        cached_data = MapCache.get_vector_data(
            data_type='trending',
            lat=request.query_params.get('latitude', 0),
            lng=request.query_params.get('longitude', 0),
            zoom=int(request.query_params.get('zoom', 10))
        )
        
        if cached_data:
            return Response(cached_data)
            
        # If not in cache, compute the data
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        
        # Transform data for heatmap visualization
        heatmap_data = []
        for area in serializer.data:
            if 'center' in area and area['center']:
                coords = area['center']['coordinates']
                # Format: [lat, lng, intensity]
                intensity = min(1.0, area['pin_count'] / 100)  # Normalize intensity
                heatmap_data.append([
                    coords[1],  # latitude
                    coords[0],  # longitude
                    intensity
                ])
        
        response_data = {
            'areas': serializer.data,
            'heatmap_data': heatmap_data,
            'visualization_params': {
                'radius': 25,
                'blur': 15,
                'max': 1.0,
                'gradient': {
                    '0.4': 'blue',
                    '0.6': 'cyan',
                    '0.7': 'lime',
                    '0.8': 'yellow',
                    '1.0': 'red'
                }
            }
        }
        
        # Cache the result
        MapCache.set_vector_data(
            data_type='trending',
            lat=request.query_params.get('latitude', 0),
            lng=request.query_params.get('longitude', 0),
            zoom=int(request.query_params.get('zoom', 10)),
            data=response_data
        )
        
        return Response(response_data)


class UserLocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for user location history (read-only)
    """
    serializer_class = UserLocationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only return the authenticated user's locations
        return UserLocation.objects.filter(user=self.request.user).order_by('-timestamp')


# New ViewSets for Vector Data

class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for building data
    """
    serializer_class = BuildingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Get bounds parameters
        try:
            north = float(self.request.query_params.get('north', 90))
            south = float(self.request.query_params.get('south', -90))
            east = float(self.request.query_params.get('east', 180))
            west = float(self.request.query_params.get('west', -180))
            zoom = int(self.request.query_params.get('zoom', 15))
            
            # Log the incoming request
            logger.info(
                'Building data requested - Bounds: N:%s, S:%s, E:%s, W:%s, Zoom:%s, User:%s',
                north, south, east, west, zoom,
                self.request.user.username if self.request.user.is_authenticated else 'Anonymous'
            )
            
            # Create cache key
            cache_key = f'buildings_bbox_{north}_{south}_{east}_{west}_{zoom}'
            
            # Try to get from cache
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info('Building data served from cache for key: %s', cache_key)
                return cached_data
                
            # Create a polygon from the bounds
            bounds = Polygon.from_bbox((west, south, east, north))
            
            # Adjust detail level based on zoom
            if zoom < 14:
                logger.debug('Low zoom level (%s) - serving simplified buildings', zoom)
                queryset = Building.objects.filter(
                    geometry__intersects=bounds
                ).simplify(
                    tolerance=0.0001
                )[:500]
            elif zoom < 16:
                logger.debug('Medium zoom level (%s) - serving medium detail buildings', zoom)
                queryset = Building.objects.filter(
                    geometry__intersects=bounds
                ).simplify(
                    tolerance=0.00005
                )[:1000]
            else:
                logger.debug('High zoom level (%s) - serving full detail buildings', zoom)
                queryset = Building.objects.filter(
                    geometry__intersects=bounds
                )[:2000]
            
            # Cache the results
            cache.set(cache_key, queryset, timeout=60*60*24)  # Cache for 24 hours
            logger.info('Building data cached with key: %s', cache_key)
            
            # Log the response size
            logger.info('Returning %d buildings for request', len(queryset))
            
            return queryset
            
        except Exception as e:
            logger.error('Error processing building request: %s', str(e))
            raise

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            response_data = serializer.data
            
            # Log response metrics
            logger.info(
                'Building data response sent - Size: %d buildings, Data size: %.2f KB',
                len(response_data),
                len(str(response_data)) / 1024
            )
            
            return Response(response_data)
        except Exception as e:
            logger.error('Error in building list endpoint: %s', str(e))
            raise


class RoadViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for road data
    """
    serializer_class = RoadSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter roads based on bounding box and zoom level
        """
        # Get query parameters
        north = self.request.query_params.get('north')
        south = self.request.query_params.get('south')
        east = self.request.query_params.get('east')
        west = self.request.query_params.get('west')
        zoom = int(self.request.query_params.get('zoom', 16))
        
        # If bounding box parameters are missing, return empty queryset
        if not all([north, south, east, west]):
            return Road.objects.none()
            
        try:
            # Create a polygon from the bounds
            bounds = Polygon.from_bbox((
                float(west), float(south), float(east), float(north)
            ))
            
            # Base queryset
            queryset = Road.objects.filter(geometry__intersects=bounds)
            
            # Filter by road type based on zoom level
            if zoom < 14:
                # For lower zoom levels, only show major roads
                return queryset.filter(
                    road_type__in=['motorway', 'trunk', 'primary', 'secondary']
                )[:300]
            elif zoom < 16:
                # For medium zoom levels, add tertiary roads
                return queryset.filter(
                    road_type__in=['motorway', 'trunk', 'primary', 'secondary', 'tertiary']
                )[:500]
            else:
                # For high zoom levels, show all roads
                return queryset[:1000]
                
        except (ValueError, TypeError, ValidationError) as e:
            logger.error(f"Error in RoadViewSet.get_queryset: {e}")
            return Road.objects.none()
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to add caching
        """
        # Similar caching logic as BuildingViewSet
        lat = (float(request.query_params.get('north', 0)) + 
              float(request.query_params.get('south', 0))) / 2
        lng = (float(request.query_params.get('east', 0)) + 
              float(request.query_params.get('west', 0))) / 2
        zoom = int(request.query_params.get('zoom', 16))
        
        additional_params = {
            'n': request.query_params.get('north'),
            's': request.query_params.get('south'),
            'e': request.query_params.get('east'),
            'w': request.query_params.get('west')
        }
        
        cached_data = MapCache.get_vector_data(
            data_type='roads',
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=additional_params
        )
        
        if cached_data:
            return Response(cached_data)
            
        queryset = self.get_queryset()
        serializer = self.get_serializer(
            queryset, 
            many=True, 
            context={'zoom': zoom}
        )
        data = serializer.data
        
        MapCache.set_vector_data(
            data_type='roads',
            lat=lat,
            lng=lng,
            zoom=zoom,
            data=data,
            additional_params=additional_params
        )
        
        return Response(data)


class ParkViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for park data
    """
    serializer_class = ParkSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter parks based on bounding box
        """
        # Same logic as BuildingViewSet with park-specific adjustments
        north = self.request.query_params.get('north')
        south = self.request.query_params.get('south')
        east = self.request.query_params.get('east')
        west = self.request.query_params.get('west')
        zoom = int(self.request.query_params.get('zoom', 16))
        
        if not all([north, south, east, west]):
            return Park.objects.none()
            
        try:
            bounds = Polygon.from_bbox((
                float(west), float(south), float(east), float(north)
            ))
            
            queryset = Park.objects.filter(geometry__intersects=bounds)
            
            # For parks, we might want to prioritize larger parks at lower zoom levels
            if zoom < 14:
                return queryset.order_by('-geometry__area')[:100]
            elif zoom < 16:
                return queryset.order_by('-geometry__area')[:200]
            else:
                return queryset[:500]
                
        except (ValueError, TypeError, ValidationError) as e:
            logger.error(f"Error in ParkViewSet.get_queryset: {e}")
            return Park.objects.none()
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to add caching
        """
        # Similar caching logic as BuildingViewSet
        lat = (float(request.query_params.get('north', 0)) + 
              float(request.query_params.get('south', 0))) / 2
        lng = (float(request.query_params.get('east', 0)) + 
              float(request.query_params.get('west', 0))) / 2
        zoom = int(request.query_params.get('zoom', 16))
        
        additional_params = {
            'n': request.query_params.get('north'),
            's': request.query_params.get('south'),
            'e': request.query_params.get('east'),
            'w': request.query_params.get('west')
        }
        
        cached_data = MapCache.get_vector_data(
            data_type='parks',
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=additional_params
        )
        
        if cached_data:
            return Response(cached_data)
            
        queryset = self.get_queryset()
        serializer = self.get_serializer(
            queryset, 
            many=True, 
            context={'zoom': zoom}
        )
        data = serializer.data
        
        MapCache.set_vector_data(
            data_type='parks',
            lat=lat,
            lng=lng,
            zoom=zoom,
            data=data,
            additional_params=additional_params
        )
        
        return Response(data)


class UserMapSettingsViewSet(viewsets.ModelViewSet):
    """
    API viewset for user map settings
    """
    serializer_class = UserMapSettingsSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return only the current user's settings
        """
        return UserMapSettings.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Ensure settings are associated with the current user
        """
        serializer.save(user=self.request.user)
    
    def retrieve(self, request, *args, **kwargs):
        """
        Get settings for the current user, creating default settings if none exist
        """
        try:
            settings = UserMapSettings.objects.get(user=request.user)
            serializer = self.get_serializer(settings)
            return Response(serializer.data)
        except UserMapSettings.DoesNotExist:
            # Create default settings
            settings = UserMapSettings.objects.create(user=request.user)
            serializer = self.get_serializer(settings)
            return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """
        Get settings for the current user, creating default settings if none exist
        """
        return self.retrieve(request)


# Tile proxy view
class OSMTileView(APIView):
    """
    Proxy view for OpenStreetMap tiles with caching and rate limiting
    Compliant with OSM Tile Usage Policy: https://operations.osmfoundation.org/policies/tiles/
    """
    authentication_classes = []  # No authentication required
    permission_classes = []  # No permissions required
    
    # OSM tile server configuration
    OSM_TILE_URL = "https://tile.openstreetmap.org"
    MAX_RETRIES = 3
    BASE_TIMEOUT = 10
    MAX_ZOOM = 19  # OSM's max zoom level
    
    def get_authenticators(self):
        return []
    
    def get_permissions(self):
        return []
    
    def validate_tile_request(self, z, x, y):
        """Validate tile coordinates and zoom level"""
        try:
            z, x, y = int(z), int(x), int(y)
            if not (0 <= z <= self.MAX_ZOOM):
                return False, "Invalid zoom level"
            if not (0 <= x < 2**z and 0 <= y < 2**z):
                return False, "Invalid tile coordinates"
            return True, None
        except ValueError:
            return False, "Invalid coordinate format"
    
    def get_osm_headers(self):
        """Get headers required by OSM tile server"""
        return {
            'User-Agent': 'BOPMaps/1.0 (+https://bopmaps.com)',  # Required by OSM
            'Accept': 'image/png',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://bopmaps.com',
            'If-Modified-Since': None,  # Will be set if we have cached data
            'If-None-Match': None  # Will be set if we have an ETag
        }
    
    def add_response_headers(self, response, source="cache"):
        """Add standard response headers"""
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Max-Age"] = "1000"
        response["Access-Control-Allow-Headers"] = "X-Requested-With, Content-Type"
        
        if source == "osm":
            # For fresh tiles from OSM, cache for 7 days (OSM recommendation)
            response["Cache-Control"] = "public, max-age=604800"
        else:
            # For cached tiles, allow caching for 30 days
            response["Cache-Control"] = "public, max-age=2592000"
        
        return response
    
    def get(self, request, z, x, y, format=None):
        """Get a map tile, either from cache or from OSM"""
        # Validate request
        is_valid, error_message = self.validate_tile_request(z, x, y)
        if not is_valid:
            logger.warning(f"Invalid tile request: {error_message} - z={z}, x={x}, y={y}")
            return HttpResponse(status=400, content=error_message)

        # Check cache first
        osm_tile_key = f"osm_tile:{z}:{x}:{y}"
        cached_data = MapCache.get_tile(z, x, y)
        # Get ETag directly from the cache to ensure we're using the right key
        cached_etag = cache.get(f"{osm_tile_key}:metadata:etag")
        logger.info(f"Cached ETag from database: '{cached_etag}'")
        
        # Handle conditional requests with If-None-Match header
        if cached_etag and 'HTTP_IF_NONE_MATCH' in request.META:
            client_etag = request.META['HTTP_IF_NONE_MATCH']
            
            # Normalize ETags by removing quotes
            client_etag_clean = client_etag.replace('"', '')
            cached_etag_clean = cached_etag.replace('"', '')
            
            logger.info(f"HTTP_IF_NONE_MATCH: '{request.META['HTTP_IF_NONE_MATCH']}'")
            logger.info(f"Normalized ETags - Client: '{client_etag_clean}' vs Cached: '{cached_etag_clean}'")
            
            # Compare the ETags after normalization
            if client_etag_clean == cached_etag_clean:
                # Return 304 Not Modified with appropriate headers
                logger.info(f"Returning 304 Not Modified for tile z={z}, x={x}, y={y}")
                response = HttpResponse(status=304)
                self.add_response_headers(response, source="cache")
                response["ETag"] = client_etag  # Use the client's format for consistency
                return response
            else:
                logger.info(f"ETag mismatch for tile z={z}, x={x}, y={y}")
        elif 'HTTP_IF_NONE_MATCH' in request.META:
            logger.info(f"If-None-Match header present, but no cached ETag: {request.META['HTTP_IF_NONE_MATCH']}")
        elif cached_etag:
            logger.info(f"Cached ETag present, but no If-None-Match header: {cached_etag}")
        
        if cached_data:
            response = HttpResponse(cached_data, content_type="image/png")
            self.add_response_headers(response, source="cache")
            if cached_etag:
                response["ETag"] = cached_etag
            return response
        
        # Prepare headers for OSM request
        headers = self.get_osm_headers()
        if cached_etag:
            headers['If-None-Match'] = cached_etag
        
        # Fetch from OSM with retries
        osm_url = f"{self.OSM_TILE_URL}/{z}/{x}/{y}.png"
        
        for attempt in range(self.MAX_RETRIES):
            try:
                current_timeout = self.BASE_TIMEOUT * (attempt + 1)  # Progressive timeout
                response = requests.get(
                    osm_url,
                    headers=headers,
                    stream=True,
                    timeout=current_timeout
                )
                
                if response.status_code == 200:
                    # Store in cache with metadata
                    logger.info(f"Response headers: {response.headers}")
                    MapCache.set_tile(z, x, y, response.content)
                    if 'ETag' in response.headers:
                        etag_value = response.headers['ETag']
                        logger.info(f"Storing ETag: {etag_value} for z={z}, x={x}, y={y}")
                        # Store the ETag directly using the actual tile coordinates
                        etag_cache_key = f"osm_tile:{z}:{x}:{y}"
                        # We store the ETag as-is to ensure we can properly handle it
                        # during conditional requests
                        cache.set(f"{etag_cache_key}:metadata:etag", etag_value, timeout=CACHE_TIMEOUTS['tile'])
                    else:
                        logger.warning(f"No ETag in response headers for z={z}, x={x}, y={y}")
                    
                    # Return response
                    tile_response = HttpResponse(response.content, content_type="image/png")
                    self.add_response_headers(tile_response, source="osm")
                    if 'ETag' in response.headers:
                        tile_response["ETag"] = response.headers["ETag"]
                    return tile_response
                
                elif response.status_code == 304:
                    # Tile hasn't changed, use cached version
                    if cached_data:
                        response = HttpResponse(cached_data, content_type="image/png")
                        self.add_response_headers(response, source="cache")
                        if cached_etag:
                            response["ETag"] = cached_etag
                        return response
                    # If we get here, something's wrong with our cache
                    logger.error(f"304 received but no cached data available: z={z}, x={x}, y={y}")
                    
                elif response.status_code == 404:
                    logger.warning(f"OSM tile not found: z={z}, x={x}, y={y}")
                    return HttpResponse(status=404)
                
                elif response.status_code == 429:
                    logger.warning(f"OSM rate limit exceeded (attempt {attempt + 1}): z={z}, x={x}, y={y}")
                    if attempt < self.MAX_RETRIES - 1:
                        import time
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return HttpResponse(status=429, content="Rate limit exceeded")
                
                else:
                    logger.warning(f"OSM tile request failed with status {response.status_code}: z={z}, x={x}, y={y}")
                    if attempt < self.MAX_RETRIES - 1:
                        continue
                    return HttpResponse(status=response.status_code)
                
            except requests.exceptions.Timeout:
                logger.warning(f"OSM tile request timed out (attempt {attempt + 1}): z={z}, x={x}, y={y}")
                if attempt < self.MAX_RETRIES - 1:
                    continue
                return HttpResponse(status=504)  # Gateway Timeout
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching OSM tile: {str(e)}")
                if attempt < self.MAX_RETRIES - 1:
                    continue
                return HttpResponse(status=500)
        
        return HttpResponse(status=503)  # Service Unavailable after all retries
    
    def options(self, request, *args, **kwargs):
        """Handle preflight requests"""
        response = HttpResponse()
        self.add_response_headers(response)
        return response
