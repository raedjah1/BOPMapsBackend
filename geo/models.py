from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings

# Create your models here.

class TrendingArea(models.Model):
    """
    Model representing areas with high pin activity
    """
    name = models.CharField(max_length=100)
    center = gis_models.PointField(geography=True)
    radius = models.IntegerField(default=800)  # meters
    pin_count = models.IntegerField(default=0)
    top_genres = models.JSONField(default=list)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.pin_count} pins)"


class UserLocation(models.Model):
    """
    Model to track user location history
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='location_history'
    )
    location = gis_models.PointField(geography=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        
    def __str__(self):
        return f"{self.user.username} at {self.timestamp}"
