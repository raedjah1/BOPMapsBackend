from django.db import models
from django.contrib.gis.db import models as gis_models
from django.conf import settings
from django.utils import timezone

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


# New models for vector data

class Building(models.Model):
    """
    Model for storing building data from OpenStreetMap
    """
    osm_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    levels = models.IntegerField(null=True, blank=True)
    building_type = models.CharField(max_length=50, null=True, blank=True)
    geometry = gis_models.GeometryField(srid=4326)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['osm_id']),
            models.Index(fields=['building_type']),
            models.Index(name='building_geom_idx', fields=['geometry']),
        ]
    
    def __str__(self):
        return f"Building {self.osm_id}" + (f": {self.name}" if self.name else "")


class Road(models.Model):
    """
    Model for storing road data from OpenStreetMap
    """
    osm_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    road_type = models.CharField(max_length=50)
    width = models.FloatField(null=True, blank=True)
    lanes = models.IntegerField(null=True, blank=True)
    geometry = gis_models.LineStringField(srid=4326)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['osm_id']),
            models.Index(fields=['road_type']),
            models.Index(name='road_geom_idx', fields=['geometry']),
        ]
    
    def __str__(self):
        return f"Road {self.osm_id}" + (f": {self.name}" if self.name else "")


class Park(models.Model):
    """
    Model for storing park and leisure area data from OpenStreetMap
    """
    osm_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    park_type = models.CharField(max_length=50)
    geometry = gis_models.GeometryField(srid=4326)
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['osm_id']),
            models.Index(fields=['park_type']),
            models.Index(name='park_geom_idx', fields=['geometry']),
        ]
    
    def __str__(self):
        return f"Park {self.osm_id}" + (f": {self.name}" if self.name else "")


class CachedTile(models.Model):
    """Model for caching map tiles with cleanup tracking"""
    z = models.IntegerField()  # zoom level
    x = models.IntegerField()  # x coordinate
    y = models.IntegerField()  # y coordinate
    data = models.BinaryField()  # tile image data
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    access_count = models.IntegerField(default=0)
    size_bytes = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['z', 'x', 'y']),
            models.Index(fields=['last_accessed']),
            models.Index(fields=['access_count']),
        ]
        unique_together = ('z', 'x', 'y')

    def update_access(self):
        self.last_accessed = timezone.now()
        self.access_count += 1
        self.save()

class CachedRegion(models.Model):
    """Model for tracking cached region bundles"""
    name = models.CharField(max_length=255)
    north = models.FloatField()
    south = models.FloatField()
    east = models.FloatField()
    west = models.FloatField()
    min_zoom = models.IntegerField()
    max_zoom = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    access_count = models.IntegerField(default=0)
    bundle_file = models.FileField(upload_to='region_bundles/')
    size_bytes = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=['last_accessed']),
            models.Index(fields=['access_count']),
        ]

    def update_access(self):
        self.last_accessed = timezone.now()
        self.access_count += 1
        self.save()

class CacheStatistics(models.Model):
    """Model for tracking cache usage statistics"""
    timestamp = models.DateTimeField(auto_now_add=True)
    total_tiles = models.IntegerField()
    total_regions = models.IntegerField()
    total_size_bytes = models.BigIntegerField()
    cleanup_runs = models.IntegerField(default=0)
    tiles_cleaned = models.IntegerField(default=0)
    regions_cleaned = models.IntegerField(default=0)
    space_reclaimed_bytes = models.BigIntegerField(default=0)

    class Meta:
        get_latest_by = 'timestamp'

class UserMapSettings(models.Model):
    """
    Model for storing user map preferences
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    show_feature_info = models.BooleanField(default=False)
    use_3d_buildings = models.BooleanField(default=True)
    default_latitude = models.FloatField(default=40.7128)  # New York
    default_longitude = models.FloatField(default=-74.0060)  # New York
    default_zoom = models.FloatField(default=15.0)
    max_cache_size_mb = models.IntegerField(default=500)
    theme = models.CharField(max_length=20, default='light')
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Map Settings for {self.user.username}"
