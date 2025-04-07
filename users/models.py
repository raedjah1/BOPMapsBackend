from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.gis.db import models as gis_models

class User(AbstractUser):
    """
    Custom User model that extends Django's AbstractUser
    with additional fields for BOPMaps functionality.
    """
    email = models.EmailField(unique=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    location = gis_models.PointField(geography=True, blank=True, null=True)
    last_active = models.DateTimeField(auto_now=True)
    spotify_connected = models.BooleanField(default=False)
    apple_music_connected = models.BooleanField(default=False)
    soundcloud_connected = models.BooleanField(default=False)
    
    def __str__(self):
        return self.username
