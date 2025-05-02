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
from cache_system import MapCache, SpatialCache

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
        """
        Filter buildings based on bounding box and zoom level
        """
        # Get query parameters
        north = self.request.query_params.get('north')
        south = self.request.query_params.get('south')
        east = self.request.query_params.get('east')
        west = self.request.query_params.get('west')
        zoom = int(self.request.query_params.get('zoom', 16))
        
        # If bounding box parameters are missing, return empty queryset
        if not all([north, south, east, west]):
            return Building.objects.none()
            
        try:
            # Create a polygon from the bounds
            bounds = Polygon.from_bbox((
                float(west), float(south), float(east), float(north)
            ))
            
            # Base queryset
            queryset = Building.objects.filter(geometry__intersects=bounds)
            
            # Limit results based on zoom level to prevent excessive data transfer
            if zoom < 14:
                return queryset.order_by('-height')[:200]  # Prioritize taller buildings
            elif zoom < 16:
                return queryset.order_by('-height')[:500]
            else:
                return queryset.order_by('-height')[:1000]
                
        except (ValueError, TypeError, ValidationError) as e:
            logger.error(f"Error in BuildingViewSet.get_queryset: {e}")
            return Building.objects.none()
    
    def list(self, request, *args, **kwargs):
        """
        Override list method to add caching
        """
        # Try to get from cache first
        lat = (float(request.query_params.get('north', 0)) + 
              float(request.query_params.get('south', 0))) / 2
        lng = (float(request.query_params.get('east', 0)) + 
              float(request.query_params.get('west', 0))) / 2
        zoom = int(request.query_params.get('zoom', 16))
        
        # Create additional params for cache key
        additional_params = {
            'n': request.query_params.get('north'),
            's': request.query_params.get('south'),
            'e': request.query_params.get('east'),
            'w': request.query_params.get('west')
        }
        
        # Try to get from cache
        cached_data = MapCache.get_vector_data(
            data_type='buildings',
            lat=lat,
            lng=lng,
            zoom=zoom,
            additional_params=additional_params
        )
        
        if cached_data:
            return Response(cached_data)
            
        # If not in cache, fetch from database
        queryset = self.get_queryset()
        serializer = self.get_serializer(
            queryset, 
            many=True, 
            context={'zoom': zoom}
        )
        data = serializer.data
        
        # Cache the result
        MapCache.set_vector_data(
            data_type='buildings',
            lat=lat,
            lng=lng,
            zoom=zoom,
            data=data,
            additional_params=additional_params
        )
        
        return Response(data)


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
    Proxy view for OpenStreetMap tiles with caching
    """
    permission_classes = []  # Public access for tiles
    
    def get(self, request, z, x, y, format=None):
        """
        Get a map tile, either from cache or from OSM
        """
        # Check cache first
        cached_tile = MapCache.get_tile(z, x, y)
        if cached_tile:
            return HttpResponse(cached_tile, content_type="image/png")
        
        # If not in cache, fetch from OSM
        osm_url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        
        try:
            response = requests.get(osm_url, stream=True, timeout=5)
            
            if response.status_code == 200:
                # Store in cache
                MapCache.set_tile(z, x, y, response.content)
                return HttpResponse(response.content, content_type="image/png")
            else:
                logger.warning(f"OSM tile request failed: {response.status_code}")
                return HttpResponse(status=response.status_code)
                
        except requests.RequestException as e:
            logger.error(f"Error fetching OSM tile: {e}")
            return HttpResponse(status=500)
