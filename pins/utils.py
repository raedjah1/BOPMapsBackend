import logging
from datetime import timedelta
from django.utils import timezone
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance
from django.db.models import Count, F, Q
from django.conf import settings
from .models import Pin, PinInteraction

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
    from django.contrib.gis.geos import Point
    
    try:
        user_location = Point(float(lng), float(lat))
        
        # Filter pins
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
        ).order_by('distance')[:limit]
        
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
            
        logger.info(f"User {user.username} {interaction_type} pin {pin.id}")
        return interaction
        
    except Exception as e:
        logger.error(f"Error recording pin interaction: {str(e)}")
        raise


def get_trending_pins(days=7, limit=20):
    """
    Get trending pins based on interaction count.
    
    Args:
        days: Number of days to look back
        limit: Maximum number of pins to return
        
    Returns:
        Queryset of Pin objects ordered by interaction count
    """
    try:
        # Set timeframe
        since = timezone.now() - timedelta(days=days)
        
        # Get pins with most interactions in the timeframe - Complete rewrite
        recent_pins = Pin.objects.filter(created_at__gte=since)
        active_pins = recent_pins.filter(Q(expiration_date__isnull=True) | Q(expiration_date__gt=timezone.now()))
        public_pins = active_pins.filter(is_private=False)
        
        # Annotate with interaction count
        trending_pins = public_pins.annotate(
            interaction_count=Count('interactions', filter=Q(interactions__created_at__gte=since))
        )
        
        # Order and limit
        result = trending_pins.order_by('-interaction_count', '-created_at')[:limit]
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_trending_pins: {str(e)}")
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


def get_clustered_pins(user, lat, lng, zoom, radius_meters=2000):
    """
    Get pins for map display with cluster parameters based on zoom level
    
    Args:
        user: The user making the request
        lat: Latitude of center
        lng: Longitude of center
        zoom: Current map zoom level
        radius_meters: Search radius in meters
        
    Returns:
        Dict with pins and cluster parameters
    """
    from django.contrib.gis.geos import Point
    
    try:
        # Adjust radius based on zoom
        zoom = int(zoom)
        if zoom < 12:
            radius_meters = min(radius_meters, 5000)
            max_pins = 100
            cluster_distance = 80
        elif zoom < 15:
            radius_meters = min(radius_meters, 2000)
            max_pins = 200
            cluster_distance = 50
        else:
            radius_meters = min(radius_meters, 1000)
            max_pins = 300
            cluster_distance = 30
        
        user_location = Point(float(lng), float(lat))
        
        # Get pins as usual
        pins = get_nearby_pins(
            user=user,
            lat=float(lat),
            lng=float(lng),
            radius_meters=radius_meters,
            limit=max_pins
        )
        
        # Return pins with clustering parameters
        return {
            'pins': pins,
            'cluster_params': {
                'enabled': zoom < 16,
                'distance': cluster_distance,
                'max_cluster_radius': 120 if zoom < 13 else 80
            }
        }
        
    except Exception as e:
        logger.error(f"Error in get_clustered_pins: {str(e)}")
        raise 