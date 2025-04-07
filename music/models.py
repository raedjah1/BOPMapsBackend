from django.db import models
from django.conf import settings

# Create your models here.

class Genre(models.Model):
    """
    Model representing music genres
    """
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name


class MusicService(models.Model):
    """
    Model to store user's connections to music services
    """
    SERVICE_TYPES = (
        ('spotify', 'Spotify'),
        ('apple', 'Apple Music'),
        ('soundcloud', 'SoundCloud')
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='music_services'
    )
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)
    access_token = models.CharField(max_length=1024)
    refresh_token = models.CharField(max_length=1024, blank=True, null=True)
    expires_at = models.DateTimeField()
    
    class Meta:
        unique_together = ('user', 'service_type')
    
    def __str__(self):
        return f"{self.user.username} - {self.service_type}"
        
        
class RecentTrack(models.Model):
    """
    Model to store tracks recently played by a user
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recent_tracks'
    )
    track_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    album = models.CharField(max_length=255, blank=True, null=True)
    album_art = models.URLField(blank=True, null=True)
    service = models.CharField(max_length=20, choices=MusicService.SERVICE_TYPES)
    played_at = models.DateTimeField()
    
    class Meta:
        ordering = ['-played_at']
    
    def __str__(self):
        return f"{self.title} - {self.artist} (played by {self.user.username})"
