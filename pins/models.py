from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings

class Pin(models.Model):
    """
    Model representing a music pin dropped at a physical location.
    """
    SERVICES = (
        ('spotify', 'Spotify'),
        ('apple', 'Apple Music'),
        ('soundcloud', 'SoundCloud')
    )
    
    RARITY_LEVELS = (
        ('common', 'Common'),
        ('uncommon', 'Uncommon'),
        ('rare', 'Rare'),
        ('epic', 'Epic'),
        ('legendary', 'Legendary')
    )
    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pins'
    )
    location = gis_models.PointField(geography=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    # Music data
    track_title = models.CharField(max_length=255)
    track_artist = models.CharField(max_length=255)
    album = models.CharField(max_length=255, blank=True, null=True)
    track_url = models.URLField()
    service = models.CharField(max_length=20, choices=SERVICES)
    
    # Customization & Gamification
    skin = models.ForeignKey(
        'gamification.PinSkin',
        on_delete=models.SET_DEFAULT,
        default=1
    )
    rarity = models.CharField(
        max_length=20,
        choices=RARITY_LEVELS,
        default='common'
    )
    
    # Discovery
    aura_radius = models.IntegerField(default=50)  # meters
    is_private = models.BooleanField(default=False)
    expiration_date = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} by {self.owner.username} - {self.track_title}"


class PinInteraction(models.Model):
    """
    Model for tracking user interactions with pins
    (viewed, collected, liked, shared)
    """
    INTERACTION_TYPES = (
        ('view', 'Viewed'),
        ('collect', 'Collected'),
        ('like', 'Liked'),
        ('share', 'Shared')
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pin_interactions'
    )
    pin = models.ForeignKey(
        Pin,
        on_delete=models.CASCADE,
        related_name='interactions'
    )
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'pin', 'interaction_type')
        
    def __str__(self):
        return f"{self.user.username} {self.interaction_type} {self.pin.title}"
