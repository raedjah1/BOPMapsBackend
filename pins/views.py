from django.shortcuts import render
from django.db import transaction
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.db import models
from rest_framework import status, viewsets, mixins
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .models import Pin, PinInteraction
from .serializers import PinSerializer, PinGeoSerializer, PinInteractionSerializer
from .utils import get_nearby_pins, record_pin_interaction, get_trending_pins, check_pin_visibility

from bopmaps.views import BaseModelViewSet
from bopmaps.permissions import IsOwnerOrReadOnly
from bopmaps.utils import create_error_response
import logging

logger = logging.getLogger('bopmaps')

class PinViewSet(BaseModelViewSet):
    """
    API viewset for Pin CRUD operations
    """
    queryset = Pin.objects.all()
    serializer_class = PinSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_serializer_class(self):
        if self.action == 'list_map' or self.action == 'nearby':
            return PinGeoSerializer
        return PinSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter expired pins
        queryset = queryset.filter(
            models.Q(expiration_date__isnull=True) | 
            models.Q(expiration_date__gt=timezone.now())
        )
        
        # Filter private pins (only show user's own private pins)
        if self.action in ['list', 'list_map', 'nearby']:
            queryset = queryset.filter(
                models.Q(is_private=False) | 
                models.Q(owner=self.request.user)
            )
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def list_map(self, request):
        """
        Get pins for map display, optimized for performance
        """
        try:
            queryset = self.get_queryset()
            lat = request.query_params.get('latitude')
            lng = request.query_params.get('longitude')
            radius = request.query_params.get('radius', 1000)
            
            try:
                radius = int(radius)
                if radius > 5000:  # Limit maximum radius
                    radius = 5000
            except (ValueError, TypeError):
                radius = 1000
                
            # If location is provided, filter by distance
            if lat and lng:
                try:
                    pins = get_nearby_pins(
                        user=request.user,
                        lat=float(lat),
                        lng=float(lng),
                        radius_meters=radius
                    )
                except (ValueError, TypeError):
                    return create_error_response("Invalid coordinates", status.HTTP_400_BAD_REQUEST)
            else:
                # No location - return recent pins with a limit
                pins = queryset.order_by('-created_at')[:100]
                
            serializer = self.get_serializer(pins, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in list_map: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    @action(detail=False, methods=['get'])
    def nearby(self, request):
        """
        Get pins near a specific location
        """
        try:
            lat = request.query_params.get('latitude')
            lng = request.query_params.get('longitude')
            radius = request.query_params.get('radius', 1000)
            
            if not lat or not lng:
                return create_error_response("Latitude and longitude are required", status.HTTP_400_BAD_REQUEST)
                
            try:
                radius = int(radius)
                if radius > 5000:  # Limit maximum radius
                    radius = 5000
            except (ValueError, TypeError):
                radius = 1000
                
            try:
                pins = get_nearby_pins(
                    user=request.user,
                    lat=float(lat),
                    lng=float(lng),
                    radius_meters=radius
                )
            except (ValueError, TypeError):
                return create_error_response("Invalid coordinates", status.HTTP_400_BAD_REQUEST)
                
            serializer = self.get_serializer(pins, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in nearby pins: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        """
        Get trending pins based on interaction count
        """
        try:
            days = request.query_params.get('days', 7)
            limit = request.query_params.get('limit', 20)
            
            try:
                days = int(days)
                limit = int(limit)
                if limit > 100:  # Limit maximum results
                    limit = 100
            except (ValueError, TypeError):
                days = 7
                limit = 20
                
            pins = get_trending_pins(days=days, limit=limit)
            serializer = PinSerializer(pins, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in trending pins: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def view(self, request, pk=None):
        """
        Record a view interaction with a pin
        """
        return self._record_interaction(request, pk, 'view')
    
    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        """
        Record a like interaction with a pin
        """
        return self._record_interaction(request, pk, 'like')
    
    @action(detail=True, methods=['post'])
    def collect(self, request, pk=None):
        """
        Record a collect interaction with a pin
        """
        return self._record_interaction(request, pk, 'collect')
    
    @action(detail=True, methods=['post'])
    def share(self, request, pk=None):
        """
        Record a share interaction with a pin
        """
        return self._record_interaction(request, pk, 'share')
    
    def _record_interaction(self, request, pk, interaction_type):
        """
        Helper method to record pin interactions
        """
        try:
            pin = self.get_object()
            
            # Check if the pin is visible to the user
            if not check_pin_visibility(pin, request.user):
                return create_error_response("Pin is not available", status.HTTP_404_NOT_FOUND)
                
            # Record the interaction
            interaction = record_pin_interaction(
                user=request.user,
                pin=pin,
                interaction_type=interaction_type
            )
            
            # For collect interaction, increment the user's pins_collected count
            if interaction_type == 'collect':
                with transaction.atomic():
                    request.user.increment_pins_collected()
                    
            return Response({
                "success": True,
                "message": f"Pin {interaction_type} recorded successfully"
            })
            
        except Exception as e:
            logger.error(f"Error recording pin {interaction_type}: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


class PinInteractionViewSet(mixins.CreateModelMixin,
                           mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """
    API viewset for Pin Interactions
    Limited to create, list, and retrieve operations
    """
    queryset = PinInteraction.objects.all()
    serializer_class = PinInteractionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Only show the user's own interactions
        queryset = queryset.filter(user=self.request.user)
        
        # Filter by interaction type if provided
        interaction_type = self.request.query_params.get('type')
        if interaction_type:
            queryset = queryset.filter(interaction_type=interaction_type)
            
        return queryset
    
    def perform_create(self, serializer):
        """
        Set the user when creating an interaction
        """
        try:
            with transaction.atomic():
                interaction = serializer.save(user=self.request.user)
                
                # For collect interaction, increment the user's pins_collected count
                if interaction.interaction_type == 'collect':
                    self.request.user.increment_pins_collected()
                    
                logger.info(f"Created pin interaction: {interaction.user.username} {interaction.interaction_type} pin {interaction.pin.id}")
        except Exception as e:
            logger.error(f"Error creating pin interaction: {str(e)}")
            raise
