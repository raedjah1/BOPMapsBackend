"""
Views for region bundle management and offline data access
"""

import os
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.gis.geos import Polygon
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework import viewsets, status, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from celery.result import AsyncResult

from .models import CachedRegion
from .serializers import CachedRegionSerializer
from .tasks import create_region_bundle

class RegionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for cached region management
    """
    serializer_class = CachedRegionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter by bounds if provided
        """
        queryset = CachedRegion.objects.all()
        
        # Filter by bounds if provided
        north = self.request.query_params.get('north')
        south = self.request.query_params.get('south')
        east = self.request.query_params.get('east')
        west = self.request.query_params.get('west')
        
        if all([north, south, east, west]):
            try:
                # Convert to float
                north = float(north)
                south = float(south)
                east = float(east)
                west = float(west)
                
                # Find regions that overlap with this bounding box
                queryset = queryset.filter(
                    north__gte=south,  # Region's north edge is above the south bound
                    south__lte=north,  # Region's south edge is below the north bound
                    east__gte=west,    # Region's east edge is right of the west bound
                    west__lte=east     # Region's west edge is left of the east bound
                )
                
            except (ValueError, TypeError) as e:
                pass
                
        return queryset.order_by('-created_at')
    
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download a region bundle file
        """
        region = self.get_object()
        
        if not region.bundle_file:
            return Response(
                {"error": "No bundle file available for this region"},
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Return the file
        try:
            return FileResponse(
                region.bundle_file.open('rb'),
                as_attachment=True,
                filename=os.path.basename(region.bundle_file.name)
            )
        except Exception as e:
            return Response(
                {"error": f"Error accessing bundle file: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegionBundleTaskView(APIView):
    """
    API for creating and checking region bundles
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        """
        Create a new region bundle
        """
        # Validate required parameters
        required = ['north', 'south', 'east', 'west']
        if not all(param in request.data for param in required):
            return Response(
                {"error": f"Missing required parameters. Required: {', '.join(required)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get parameters
        north = float(request.data.get('north'))
        south = float(request.data.get('south'))
        east = float(request.data.get('east'))
        west = float(request.data.get('west'))
        min_zoom = int(request.data.get('min_zoom', 10))
        max_zoom = int(request.data.get('max_zoom', 18))
        name = request.data.get('name')
        
        # Validate bounds
        if north <= south or east <= west:
            return Response(
                {"error": "Invalid bounds. North must be > South, East must be > West"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Validate zoom levels
        if min_zoom < 0 or max_zoom > 19 or min_zoom > max_zoom:
            return Response(
                {"error": "Invalid zoom levels. Must be 0-19, and min_zoom <= max_zoom"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Create bundle task
        task = create_region_bundle.delay(
            north=north,
            south=south,
            east=east,
            west=west,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            name=name
        )
        
        # Return task ID for status polling
        return Response({"task_id": task.id})
    
    def get(self, request, task_id=None, format=None):
        """
        Check status of a region bundle task
        """
        if not task_id:
            return Response(
                {"error": "Task ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get task status
        task = AsyncResult(task_id)
        
        # Format the response
        response = {
            "task_id": task_id,
            "status": task.status,
        }
        
        # Add result or progress info
        if task.status == 'SUCCESS':
            region_id = task.result
            try:
                region = CachedRegion.objects.get(id=region_id)
                serializer = CachedRegionSerializer(region, context={'request': request})
                response["region"] = serializer.data
            except CachedRegion.DoesNotExist:
                response["region_id"] = region_id
                
        elif task.status == 'PROGRESS':
            response.update(task.info)
            
        elif task.status == 'FAILURE':
            response["error"] = str(task.result)
            
        return Response(response) 