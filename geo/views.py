from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .models import TrendingArea, UserLocation
from .serializers import TrendingAreaSerializer, UserLocationSerializer
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
import logging

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
        
        return Response({
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
        })


class UserLocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for user location history (read-only)
    """
    serializer_class = UserLocationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only return the authenticated user's locations
        return UserLocation.objects.filter(user=self.request.user).order_by('-timestamp')
