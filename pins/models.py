from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings
from django.utils.functional import cached_property
from django.contrib.postgres.fields import ArrayField

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
    
    MOOD_CHOICES = (
        ('happy', 'Happy'),
        ('chill', 'Chill'),
        ('energetic', 'Energetic'),
        ('sad', 'Sad'),
        ('romantic', 'Romantic'),
        ('focus', 'Focus'),
        ('party', 'Party'),
        ('workout', 'Workout'),
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
    
    # Enhanced discovery fields
    genre = models.CharField(max_length=50, blank=True, null=True)
    mood = models.CharField(max_length=20, choices=MOOD_CHOICES, blank=True, null=True)
    tags = ArrayField(models.CharField(max_length=50), blank=True, null=True)
    
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
    
    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['service']),
            models.Index(fields=['rarity']),
            models.Index(fields=['genre']),
            models.Index(fields=['mood']),
            models.Index(fields=['is_private']),
        ]
    
    def __str__(self):
        return f"{self.title} by {self.owner.username} - {self.track_title}"
    
    @cached_property
    def total_interactions(self):
        """Get total number of interactions with this pin"""
        return self.interactions.count()
    
    @cached_property
    def like_count(self):
        """Get number of likes for this pin"""
        return self.interactions.filter(interaction_type='like').count()
    
    @cached_property
    def collect_count(self):
        """Get number of collects for this pin"""
        return self.interactions.filter(interaction_type='collect').count()
    
    @cached_property
    def view_count(self):
        """Get number of views for this pin"""
        return self.interactions.filter(interaction_type='view').count()
    
    def find_similar_pins(self, limit=5):
        """Find similar pins based on music attributes"""
        from django.db.models import Count, Q
        
        # Start with base queryset
        qs = Pin.objects.exclude(id=self.id)
        
        # Filter by similar properties
        if self.genre:
            qs = qs.filter(genre=self.genre)
        
        if self.service:
            qs = qs.filter(service=self.service)
        
        if self.mood:
            qs = qs.filter(mood=self.mood)
        
        # Add a relevance score based on artist match
        qs = qs.extra(
            select={'artist_match': f"track_artist = '{self.track_artist}'"}
        )
        
        # Order by relevance factors
        return qs.order_by('-artist_match', '-created_at')[:limit]


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
        indexes = [
            models.Index(fields=['interaction_type']),
            models.Index(fields=['created_at']),
        ]
        
    def __str__(self):
        return f"{self.user.username} {self.interaction_type} {self.pin.title}"


class PinAnalytics(models.Model):
    """
    Model for tracking analytics data about pins
    """
    pin = models.OneToOneField(Pin, on_delete=models.CASCADE, related_name='analytics')
    total_views = models.IntegerField(default=0)
    unique_viewers = models.IntegerField(default=0)
    collection_rate = models.FloatField(default=0)
    peak_hour = models.IntegerField(default=0, help_text="Hour of day with most views (0-23)")
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Pin analytics"
    
    def __str__(self):
        return f"Analytics for {self.pin.title}"
    
    @classmethod
    def update_for_pin(cls, pin):
        """Update analytics for a pin"""
        from django.db.models import Count
        from django.utils import timezone
        from datetime import timedelta
        
        analytics, created = cls.objects.get_or_create(pin=pin)
        
        # Update metrics
        analytics.total_views = pin.interactions.filter(interaction_type='view').count()
        analytics.unique_viewers = pin.interactions.filter(interaction_type='view').values('user').distinct().count()
        
        # Calculate collection rate
        if analytics.total_views > 0:
            collect_count = pin.interactions.filter(interaction_type='collect').count()
            analytics.collection_rate = (collect_count / analytics.total_views)
        
        # Find peak hour
        recent_views = pin.interactions.filter(
            interaction_type='view',
            created_at__gte=timezone.now() - timedelta(days=7)
        )
        if recent_views.exists():
            hour_counts = recent_views.extra(
                {'hour': "EXTRACT(HOUR FROM created_at)"}
            ).values('hour').annotate(count=Count('id')).order_by('-count')
            if hour_counts:
                analytics.peak_hour = hour_counts[0]['hour']
        
        analytics.save()
        return analytics
