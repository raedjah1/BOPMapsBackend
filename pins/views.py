from django.shortcuts import render
from django.db import transaction
from django.contrib.gis.geos import Point
from django.utils import timezone
from django.db import models
from django.core.cache import cache
from rest_framework import status, viewsets, mixins
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from datetime import timedelta

from .models import Pin, PinInteraction, PinAnalytics
from .serializers import PinSerializer, PinGeoSerializer, PinInteractionSerializer, PinAnalyticsSerializer
from .utils import (
    get_nearby_pins, record_pin_interaction, get_trending_pins, 
    check_pin_visibility, get_clustered_pins, get_pins_by_relevance
)

from bopmaps.views import BaseModelViewSet
from bopmaps.permissions import IsOwnerOrReadOnly
from bopmaps.utils import create_error_response
import logging

try:
    # Try to import channels layer for WebSocket support
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False
    
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
        elif self.action == 'analytics':
            return PinAnalyticsSerializer
        return PinSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter expired pins
        queryset = queryset.filter(
            models.Q(expiration_date__isnull=True) | 
            models.Q(expiration_date__gt=timezone.now())
        )
        
        # Filter private pins (only show user's own private pins)
        if self.action in ['list', 'list_map', 'nearby', 'recommended', 'advanced_search']:
            queryset = queryset.filter(
                models.Q(is_private=False) | 
                models.Q(owner=self.request.user)
            )
        
        return queryset

    def create(self, request, *args, **kwargs):
        """Enhanced pin creation with notifications"""
        response = super().create(request, *args, **kwargs)
        
        # If successfully created, trigger notifications via WebSockets
        if response.status_code == 201 and CHANNELS_AVAILABLE:
            try:
                # Get the newly created pin
                pin = Pin.objects.get(id=response.data['id'])
                
                # Create notification message
                message = {
                    'type': 'new_pin',
                    'pin_id': pin.id,
                    'owner': pin.owner.username,
                    'title': pin.title,
                    'location': {
                        'lat': pin.location.y,
                        'lng': pin.location.x
                    }
                }
                
                # Send to the pin update channel
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    'pins_updates',
                    {
                        'type': 'broadcast_update',
                        'message': message
                    }
                )
                
                logger.info(f"Sent notification for new pin {pin.id}")
            except Exception as e:
                logger.error(f"Failed to send pin notification: {str(e)}")
        
        return response
    
    @action(detail=False, methods=['get'])
    def list_map(self, request):
        """
        Get pins for map display, optimized for performance with clustering
        """
        try:
            queryset = self.get_queryset()
            lat = request.query_params.get('latitude')
            lng = request.query_params.get('longitude')
            radius = request.query_params.get('radius', 1000)
            zoom = request.query_params.get('zoom', 13)
            
            try:
                zoom = int(zoom)
                radius = int(radius)
                
                # Dynamically adjust radius based on zoom level
                if zoom < 10:
                    max_radius = 10000
                elif zoom < 13:
                    max_radius = 5000
                else:
                    max_radius = 3000
                
                if radius > max_radius:
                    radius = max_radius
                    
            except (ValueError, TypeError):
                radius = 1000
                zoom = 13
                
            # If location is provided, use clustering approach
            if lat and lng:
                try:
                    result = get_clustered_pins(
                        user=request.user,
                        lat=float(lat),
                        lng=float(lng),
                        zoom=zoom,
                        radius_meters=radius
                    )
                    pins = result['pins']
                    
                    # Add cluster parameters to response metadata
                    cluster_params = result['cluster_params']
                    
                except (ValueError, TypeError):
                    return create_error_response("Invalid coordinates", status.HTTP_400_BAD_REQUEST)
            else:
                # No location - return recent pins with a limit
                pins = queryset.order_by('-created_at')[:100]
                cluster_params = {
                    'enabled': True,
                    'distance': 60,
                    'max_cluster_radius': 100
                }
                
            serializer = self.get_serializer(pins, many=True)
            response_data = serializer.data
            
            # Include cluster parameters in response
            return Response({
                'type': 'FeatureCollection',
                'features': response_data,
                'cluster_params': cluster_params
            })
            
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
    
    @action(detail=False, methods=['get'])
    def recommended(self, request):
        """
        Get recommended pins based on user preferences and location
        """
        try:
            lat = request.query_params.get('latitude')
            lng = request.query_params.get('longitude')
            limit = request.query_params.get('limit', 20)
            
            try:
                limit = int(limit)
                if limit > 50:
                    limit = 50
            except (ValueError, TypeError):
                limit = 20
                
            if lat and lng:
                try:
                    lat = float(lat)
                    lng = float(lng)
                except (ValueError, TypeError):
                    return create_error_response("Invalid coordinates", status.HTTP_400_BAD_REQUEST)
            else:
                # Recommendations without location are less precise
                lat = None
                lng = None
                
            pins = get_pins_by_relevance(
                user=request.user,
                lat=lat,
                lng=lng,
                limit=limit
            )
            
            serializer = PinSerializer(pins, many=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error in recommended pins: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def advanced_search(self, request):
        """
        Advanced pin search with multiple criteria
        """
        try:
            queryset = self.get_queryset()
            
            # Music service filter
            service = request.query_params.get('service')
            if service:
                queryset = queryset.filter(service=service)
                
            # Genre/mood filters
            genre = request.query_params.get('genre')
            mood = request.query_params.get('mood')
            if genre:
                queryset = queryset.filter(genre=genre)
            if mood:
                queryset = queryset.filter(mood=mood)
                
            # Artist filter
            artist = request.query_params.get('artist')
            if artist:
                queryset = queryset.filter(track_artist__icontains=artist)
                
            # Track title filter
            track = request.query_params.get('track')
            if track:
                queryset = queryset.filter(track_title__icontains=track)
                
            # Rarity filter
            rarity = request.query_params.get('rarity')
            if rarity:
                queryset = queryset.filter(rarity=rarity)
                
            # Time-based filters
            time_range = request.query_params.get('time_range')
            if time_range:
                if time_range == 'today':
                    queryset = queryset.filter(created_at__date=timezone.now().date())
                elif time_range == 'week':
                    queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=7))
                elif time_range == 'month':
                    queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=30))
                    
            # Popularity filters
            min_likes = request.query_params.get('min_likes')
            if min_likes:
                try:
                    min_likes = int(min_likes)
                    queryset = queryset.annotate(
                        like_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='like'))
                    ).filter(like_count__gte=min_likes)
                except (ValueError, TypeError):
                    pass
                    
            # Sort options
            sort_by = request.query_params.get('sort_by', 'created_at')
            if sort_by == 'likes':
                queryset = queryset.annotate(
                    like_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='like'))
                ).order_by('-like_count')
            elif sort_by == 'collects':
                queryset = queryset.annotate(
                    collect_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='collect'))
                ).order_by('-collect_count')
            elif sort_by == 'views':
                queryset = queryset.annotate(
                    view_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='view'))
                ).order_by('-view_count')
            else:
                # Default to newest first
                queryset = queryset.order_by('-created_at')
                
            # Pagination
            limit = request.query_params.get('limit', 20)
            offset = request.query_params.get('offset', 0)
            try:
                limit = int(limit)
                offset = int(offset)
                if limit > 50:
                    limit = 50
            except (ValueError, TypeError):
                limit = 20
                offset = 0
                
            queryset = queryset[offset:offset+limit]
            serializer = PinSerializer(queryset, many=True)
            
            return Response({
                'count': queryset.count(),
                'next': offset + limit if queryset.count() == limit else None,
                'previous': offset - limit if offset > 0 else None,
                'results': serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error in advanced search: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def similar(self, request, pk=None):
        """
        Find pins similar to this one
        """
        try:
            pin = self.get_object()
            
            # Check visibility
            if not check_pin_visibility(pin, request.user):
                return create_error_response("Pin is not available", status.HTTP_404_NOT_FOUND)
                
            # Get similar pins
            similar_pins = pin.find_similar_pins(limit=10)
            serializer = PinSerializer(similar_pins, many=True)
            
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error finding similar pins: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def analytics(self, request, pk=None):
        """
        Get analytics for a specific pin
        """
        try:
            pin = self.get_object()
            
            # Only pin owner can view analytics
            if pin.owner != request.user:
                return create_error_response("Not authorized to view analytics", status.HTTP_403_FORBIDDEN)
                
            # Get or create analytics
            analytics, created = PinAnalytics.objects.get_or_create(pin=pin)
            
            # Update analytics if needed
            if created or (timezone.now() - analytics.last_updated).total_seconds() > 3600:
                analytics = PinAnalytics.update_for_pin(pin)
                
            serializer = PinAnalyticsSerializer(analytics)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error getting pin analytics: {str(e)}")
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
    
    @action(detail=True, methods=['get'])
    def map_details(self, request, pk=None):
        """
        Get detailed pin information for map display with aura visualization settings
        """
        try:
            pin = self.get_object()
            
            # Check if the pin is visible to the user
            if not check_pin_visibility(pin, request.user):
                return create_error_response("Pin is not available", status.HTTP_404_NOT_FOUND)
            
            # Record view interaction if not already viewed in the last hour
            if not PinInteraction.objects.filter(
                user=request.user, 
                pin=pin, 
                interaction_type='view',
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).exists():
                record_pin_interaction(
                    user=request.user,
                    pin=pin,
                    interaction_type='view'
                )
            
            # Get details with customized serializer for map display
            serializer = PinSerializer(pin)
            data = serializer.data
            
            # Define color mapping based on music service and rarity
            service_colors = {
                'spotify': '#1DB954',
                'apple': '#FC3C44',
                'soundcloud': '#FF7700'
            }
            
            rarity_opacity = {
                'common': 0.6,
                'uncommon': 0.7,
                'rare': 0.8,
                'epic': 0.85,
                'legendary': 0.9
            }
            
            # Add visualization settings based on pin properties
            data['visualization'] = {
                'aura_color': service_colors.get(pin.service, '#3388ff'),
                'aura_opacity': rarity_opacity.get(pin.rarity, 0.7),
                'pulse_animation': pin.created_at > (timezone.now() - timedelta(hours=24)),
                'icon_url': pin.skin.image.url if hasattr(pin, 'skin') and pin.skin and pin.skin.image else None
            }
            
            return Response(data)
            
        except Exception as e:
            logger.error(f"Error getting pin map details: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def websocket_connect(self, request):
        """
        Return connection info for real-time pin updates via WebSockets
        """
        if not CHANNELS_AVAILABLE:
            return create_error_response("WebSocket support not available", status.HTTP_501_NOT_IMPLEMENTED)
            
        return Response({
            'websocket_url': 'ws://localhost:8000/ws/pins/',
            'supported_events': ['new_pin', 'trending_update']
        })
    
    @action(detail=False, methods=['post'])
    def batch_interact(self, request):
        """
        Batch process multiple pin interactions
        """
        try:
            interactions = request.data.get('interactions', [])
            results = []
            
            with transaction.atomic():
                for interaction in interactions:
                    pin_id = interaction.get('pin_id')
                    interaction_type = interaction.get('type')
                    
                    try:
                        pin = Pin.objects.get(id=pin_id)
                        if check_pin_visibility(pin, request.user):
                            record_pin_interaction(request.user, pin, interaction_type)
                            results.append({
                                'pin_id': pin_id,
                                'status': 'success'
                            })
                        else:
                            results.append({
                                'pin_id': pin_id,
                                'status': 'error',
                                'message': 'Pin not available'
                            })
                    except Exception as e:
                        results.append({
                            'pin_id': pin_id,
                            'status': 'error',
                            'message': str(e)
                        })
                        
            return Response(results)
            
        except Exception as e:
            logger.error(f"Error in batch interactions: {str(e)}")
            return create_error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
