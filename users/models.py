from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.gis.db import models as gis_models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
from bopmaps.models import TimeStampedModel, ValidationModelMixin
from bopmaps.validators import username_validator, ImageDimensionsValidator
import logging

logger = logging.getLogger('bopmaps')

class User(AbstractUser, ValidationModelMixin):
    """
    Custom User model that extends Django's AbstractUser
    with additional fields for BOPMaps functionality.
    """
    # Use our custom username validator
    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[username_validator],
        error_messages={
            'unique': "A user with that username already exists.",
        },
    )
    
    # Email is unique and case-insensitive
    email = models.EmailField(
        unique=True,
        error_messages={
            'unique': "A user with that email already exists.",
        },
    )
    
    # Profile picture with validation
    profile_pic = models.ImageField(
        upload_to='profile_pics/', 
        blank=True, 
        null=True,
        validators=[
            ImageDimensionsValidator(
                min_width=100, min_height=100,
                max_width=2000, max_height=2000
            )
        ]
    )
    
    bio = models.TextField(blank=True, null=True)
    location = gis_models.PointField(geography=True, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Music service connections
    spotify_connected = models.BooleanField(default=False)
    apple_music_connected = models.BooleanField(default=False)
    soundcloud_connected = models.BooleanField(default=False)
    
    # User preferences
    notification_enabled = models.BooleanField(default=True)
    location_tracking_enabled = models.BooleanField(default=True)
    email_notifications_enabled = models.BooleanField(default=True)
    
    # Device information
    fcm_token = models.CharField(max_length=512, blank=True, null=True)
    device_os = models.CharField(max_length=100, blank=True, null=True)
    app_version = models.CharField(max_length=20, blank=True, null=True)
    
    # Account status
    is_banned = models.BooleanField(default=False)
    ban_reason = models.TextField(null=True, blank=True)
    banned_until = models.DateTimeField(null=True, blank=True)
    
    # Stats
    pins_created = models.PositiveIntegerField(default=0)
    pins_collected = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['spotify_connected']),
            models.Index(fields=['apple_music_connected']),
            models.Index(fields=['soundcloud_connected']),
            models.Index(fields=['is_banned']),
        ]
    
    def __str__(self):
        return self.username
    
    def save(self, *args, **kwargs):
        """Override save to normalize and validate email"""
        # Convert email to lowercase
        if self.email:
            self.email = self.email.lower()
            
        super().save(*args, **kwargs)
        
    def update_last_active(self):
        """Update last active timestamp"""
        self.last_active = timezone.now()
        self.save(update_fields=['last_active'])
        
    def update_location(self, point):
        """Update user location"""
        self.location = point
        self.last_location_update = timezone.now()
        self.save(update_fields=['location', 'last_location_update'])
        
    def get_profile_pic_url(self):
        """Get the URL for the user's profile picture"""
        if self.profile_pic:
            return self.profile_pic.url
        return f"{settings.STATIC_URL}default_profile.png"
    
    def is_connected_to_music_service(self):
        """Check if user is connected to any music service"""
        return self.spotify_connected or self.apple_music_connected or self.soundcloud_connected
    
    def increment_pins_created(self):
        """Increment pins created count"""
        self.pins_created += 1
        self.save(update_fields=['pins_created'])
    
    def increment_pins_collected(self):
        """Increment pins collected count"""
        self.pins_collected += 1
        self.save(update_fields=['pins_collected'])
        
    def check_ban_status(self):
        """
        Check if the user is currently banned.
        If the ban has expired, unban the user.
        """
        if not self.is_banned:
            return False
            
        if self.banned_until and self.banned_until < timezone.now():
            self.is_banned = False
            self.banned_until = None
            self.save(update_fields=['is_banned', 'banned_until'])
            logger.info(f"User {self.username} ban has expired and been lifted.")
            return False
            
        return True
        
    def ban_user(self, reason, days=None):
        """
        Ban a user for the specified reason and duration.
        
        Args:
            reason: The reason for the ban
            days: Number of days the ban should last (None for permanent)
        """
        self.is_banned = True
        self.ban_reason = reason
        
        if days:
            self.banned_until = timezone.now() + timezone.timedelta(days=days)
        else:
            self.banned_until = None  # Permanent ban
            
        self.save(update_fields=['is_banned', 'ban_reason', 'banned_until'])
        logger.info(f"User {self.username} has been banned. Reason: {reason}, Duration: {days if days else 'permanent'} days")
        
    def unban_user(self):
        """Unban a user"""
        if self.is_banned:
            self.is_banned = False
            self.banned_until = None
            self.save(update_fields=['is_banned', 'banned_until'])
            logger.info(f"User {self.username} has been unbanned.")
            
    @property
    def full_name(self):
        """Get the user's full name or username if not available"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        return self.username
        
    @property
    def age(self):
        """Calculate user's age from date of birth"""
        if not self.date_of_birth:
            return None
            
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
