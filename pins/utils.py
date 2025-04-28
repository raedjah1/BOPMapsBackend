import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Count, F, Q, Avg, Sum
from django.conf import settings
from django.core.cache import cache
from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from .models import Pin, PinInteraction, PinAnalytics
from math import cos, radians

logger = logging.getLogger('bopmaps')

def get_nearby_pins(user, lat, lng, radius_meters=1000, limit=50):
    """
    Get pins near a given location.
    
    Args:
        user: The user making the request
        lat: Latitude of location
        lng: Longitude of location
        radius_meters: Search radius in meters
        limit: Maximum number of pins to return
        
    Returns:
        Queryset of Pin objects ordered by distance
    """
    try:
        # Generate cache key based on parameters
        cache_key = f"nearby_pins_{user.id}_{lat}_{lng}_{radius_meters}_{limit}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
            
        user_location = Point(float(lng), float(lat))
        
        # Filter pins with optimized query
        pins = Pin.objects.filter(
            # Exclude expired pins
            Q(expiration_date__isnull=True) | Q(expiration_date__gt=timezone.now()),
            # Exclude private pins from other users
            Q(is_private=False) | Q(owner=user)
        ).annotate(
            distance=Distance('location', user_location),
            like_count=Count('interactions', filter=Q(interactions__interaction_type='like')),
            collect_count=Count('interactions', filter=Q(interactions__interaction_type='collect'))
        ).filter(
            # Filter by distance
            distance__lte=D(m=radius_meters)
        ).select_related('owner', 'skin').order_by('distance')[:limit]
        
        # Cache result for 5 minutes
        cache.set(cache_key, pins, 300)
        
        return pins
        
    except Exception as e:
        logger.error(f"Error in get_nearby_pins: {str(e)}")
        raise


def record_pin_interaction(user, pin, interaction_type):
    """
    Record a user's interaction with a pin.
    
    Args:
        user: The user interacting with the pin
        pin: The pin being interacted with
        interaction_type: Type of interaction (view, collect, like, share)
        
    Returns:
        The created or updated PinInteraction object
    """
    try:
        # Check if this interaction already exists
        interaction, created = PinInteraction.objects.get_or_create(
            user=user,
            pin=pin,
            interaction_type=interaction_type
        )
        
        # If not created, just update the timestamp
        if not created:
            interaction.created_at = timezone.now()
            interaction.save(update_fields=['created_at'])
        
        # Update analytics if it's a view interaction
        if interaction_type == 'view':
            # Use a background task or async process in production
            PinAnalytics.update_for_pin(pin)
            
        logger.info(f"User {user.username} {interaction_type} pin {pin.id}")
        return interaction
        
    except Exception as e:
        logger.error(f"Error recording pin interaction: {str(e)}")
        raise


def check_pin_visibility(pin, user):
    """
    Check if a pin is visible to a specific user.
    
    Args:
        pin: The pin to check
        user: The user to check visibility for
        
    Returns:
        Boolean indicating if the pin is visible to the user
    """
    # Check if the pin is expired
    if pin.expiration_date and pin.expiration_date < timezone.now():
        return False
        
    # User can always see their own pins
    if pin.owner == user:
        return True
        
    # Private pins are only visible to their owners
    if pin.is_private:
        return False
        
    # Public pins are visible to everyone
    return True


def get_trending_pins(days=7, limit=20):
    """
    Get trending pins based on interaction count.
    
    Args:
        days: Number of days to look back
        limit: Maximum number of pins to return
        
    Returns:
        Queryset of Pin objects
    """
    try:
        # Create cache key based on parameters
        cache_key = f"trending_pins_{days}_{limit}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
            
        # Calculate date threshold
        date_threshold = timezone.now() - timedelta(days=days)
        
        # Get pins with recent interactions
        pins = Pin.objects.annotate(
            interaction_count=Count(
                'interactions',
                filter=Q(
                    interactions__created_at__gte=date_threshold
                )
            ),
            like_weight=Sum(
                'interactions__id',
                filter=Q(
                    interactions__interaction_type='like',
                    interactions__created_at__gte=date_threshold
                )
            ) * 2,
            collect_weight=Sum(
                'interactions__id',
                filter=Q(
                    interactions__interaction_type='collect',
                    interactions__created_at__gte=date_threshold
                )
            ) * 3,
            share_weight=Sum(
                'interactions__id',
                filter=Q(
                    interactions__interaction_type='share',
                    interactions__created_at__gte=date_threshold
                )
            ) * 4,
            trending_score=F('interaction_count') + F('like_weight') + F('collect_weight') + F('share_weight')
        ).filter(
            # Only include non-expired pins
            Q(expiration_date__isnull=True) | Q(expiration_date__gt=timezone.now()),
            # Exclude private pins
            is_private=False,
            # Only include pins with interactions
            interaction_count__gt=0
        ).order_by('-trending_score')[:limit]
        
        # Cache result for 15 minutes
        cache.set(cache_key, pins, 900)
        
        return pins
        
    except Exception as e:
        logger.error(f"Error in get_trending_pins: {str(e)}")
        raise


def get_viewport_bounds(lat, lng, zoom):
    """
    Calculate approximate bounds of the viewport based on location and zoom.
    
    Args:
        lat: Center latitude
        lng: Center longitude
        zoom: Map zoom level
        
    Returns:
        Polygon object representing the viewport bounds
    """
    # Calculate approximate viewport dimensions based on zoom
    # These values are approximations and may need adjustment
    zoom_to_km = {
        10: 50,  # ~50km view at zoom 10
        11: 25,
        12: 15,
        13: 7.5,
        14: 3.5,
        15: 1.5,
        16: 0.75,
        17: 0.4,
        18: 0.2
    }
    
    # Default to 75km if zoom is lower than 10
    km_width = zoom_to_km.get(zoom, 75 if zoom < 10 else 0.1)
    
    # Convert km to approximate degrees (rough estimation)
    # 1 degree latitude is ~111km, but longitude varies with latitude
    lat_delta = km_width / 111.0
    # Adjust for longitude compression at higher latitudes
    lng_delta = km_width / (111.0 * abs(cos(radians(lat))))
    
    # Create a simple box around the point
    return Polygon.from_bbox((
        lng - lng_delta,  # min_x
        lat - lat_delta,  # min_y
        lng + lng_delta,  # max_x
        lat + lat_delta   # max_y
    ))


def get_clustered_pins(user, lat, lng, zoom, radius_meters=2000):
    """
    Get pins for map display with enhanced clustering based on zoom level.
    
    Args:
        user: The user making the request
        lat: Latitude of center
        lng: Longitude of center
        zoom: Current map zoom level
        radius_meters: Search radius in meters
        
    Returns:
        Dict with pins and cluster parameters
    """
    try:
        # Generate cache key
        cache_key = f"clustered_pins_{user.id}_{lat}_{lng}_{zoom}_{radius_meters}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        # Adjust parameters based on zoom
        zoom = int(zoom)
        if zoom < 12:
            radius_meters = min(radius_meters, 5000)
            max_pins = 100
            cluster_distance = 80
            grid_size = 0.01  # Approx 1km grid at equator
        elif zoom < 15:
            radius_meters = min(radius_meters, 2000)
            max_pins = 200
            cluster_distance = 50
            grid_size = 0.005  # Approx 500m grid
        else:
            radius_meters = min(radius_meters, 1000)
            max_pins = 300
            cluster_distance = 30
            grid_size = 0.002  # Approx 200m grid
        
        user_location = Point(float(lng), float(lat))
        
        # Get pins as usual
        pins = get_nearby_pins(
            user=user,
            lat=float(lat),
            lng=float(lng),
            radius_meters=radius_meters,
            limit=max_pins
        )
        
        # For higher zoom levels, try to get pins by genre/mood
        if zoom >= 14 and len(pins) < max_pins / 2:
            # Add additional pins by genre/mood if there aren't many nearby
            user_interactions = PinInteraction.objects.filter(
                user=user,
                created_at__gte=timezone.now() - timedelta(days=30)
            ).values_list('pin_id', flat=True)
            
            # Get user's interacted pins
            user_pins = Pin.objects.filter(id__in=user_interactions)
            
            # Extract genres and moods the user has interacted with
            genres = user_pins.exclude(genre__isnull=True).values_list('genre', flat=True).distinct()
            moods = user_pins.exclude(mood__isnull=True).values_list('mood', flat=True).distinct()
            
            # Find additional pins with similar genres/moods
            if genres or moods:
                additional_pins = Pin.objects.filter(
                    # Base filter
                    Q(expiration_date__isnull=True) | Q(expiration_date__gt=timezone.now()),
                    is_private=False
                ).exclude(
                    id__in=[p.id for p in pins]  # Exclude pins we already have
                )
                
                if genres:
                    additional_pins = additional_pins.filter(genre__in=genres)
                if moods:
                    additional_pins = additional_pins.filter(mood__in=moods)
                
                # Add distance annotation and limit
                additional_pins = additional_pins.annotate(
                    distance=Distance('location', user_location)
                ).order_by('distance')[:50]
                
                # Combine with main pins
                pins = list(pins) + list(additional_pins)
        
        # Return pins with clustering parameters
        result = {
            'pins': pins,
            'cluster_params': {
                'enabled': zoom < 16,
                'distance': cluster_distance,
                'max_cluster_radius': 120 if zoom < 13 else 80,
                'grid_size': grid_size
            }
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, result, 300)
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_clustered_pins: {str(e)}")
        raise


def get_pins_by_relevance(user, lat=None, lng=None, limit=20):
    """
    Get pins relevant to a user based on their preferences.
    
    Args:
        user: The user to get relevant pins for
        lat: Optional latitude for location relevance
        lng: Optional longitude for location relevance
        limit: Maximum number of pins to return
        
    Returns:
        List of Pin objects sorted by relevance
    """
    try:
        # Start with base queryset
        queryset = Pin.objects.filter(
            # Only include non-expired pins
            Q(expiration_date__isnull=True) | Q(expiration_date__gt=timezone.now()),
            # Only include public pins
            is_private=False
        )
        
        # Get user's interaction history
        recent_interactions = PinInteraction.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(days=30)
        )
        
        # Extract genres and moods the user has interacted with
        interacted_pins = Pin.objects.filter(
            interactions__in=recent_interactions
        ).distinct()
        
        preferred_genres = list(interacted_pins.exclude(
            genre__isnull=True
        ).values_list('genre', flat=True).distinct())
        
        preferred_moods = list(interacted_pins.exclude(
            mood__isnull=True
        ).values_list('mood', flat=True).distinct())
        
        # Add relevance annotations
        if preferred_genres or preferred_moods:
            if preferred_genres:
                queryset = queryset.extra(
                    select={
                        'genre_match': f"genre IN ({','.join(repr(g) for g in preferred_genres)})"
                    }
                )
            
            if preferred_moods:
                queryset = queryset.extra(
                    select={
                        'mood_match': f"mood IN ({','.join(repr(m) for m in preferred_moods)})"
                    }
                )
            
            # Order by matches first
            if preferred_genres and preferred_moods:
                queryset = queryset.extra(
                    select={'relevance_score': 'genre_match + mood_match'}
                ).order_by('-relevance_score', '-created_at')
            elif preferred_genres:
                queryset = queryset.order_by('-genre_match', '-created_at')
            else:
                queryset = queryset.order_by('-mood_match', '-created_at')
        else:
            # Default to newest pins if no preferences
            queryset = queryset.order_by('-created_at')
        
        # Add location relevance if coordinates provided
        if lat and lng:
            user_location = Point(float(lng), float(lat))
            queryset = queryset.annotate(
                distance=Distance('location', user_location)
            )
            
            # Blend distance with other relevance factors
            if preferred_genres or preferred_moods:
                # Still prioritize preference matches, but sort by distance within matches
                if 'relevance_score' in queryset.query.extra_select:
                    queryset = queryset.order_by('-relevance_score', 'distance')
                elif preferred_genres:
                    queryset = queryset.order_by('-genre_match', 'distance')
                else:
                    queryset = queryset.order_by('-mood_match', 'distance')
            else:
                # Just sort by distance if no preferences
                queryset = queryset.order_by('distance')
        
        return queryset[:limit]
    except Exception as e:
        logger.error(f"Error in get_pins_by_relevance: {str(e)}")
        raise 