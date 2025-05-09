from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer, GeometrySerializerMethodField
from .models import TrendingArea, UserLocation, Building, Road, Park, CachedRegion, UserMapSettings
from bopmaps.serializers import BaseSerializer

class TrendingAreaSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for TrendingArea model
    """
    class Meta:
        model = TrendingArea
        geo_field = 'center'
        fields = ('id', 'name', 'radius', 'pin_count', 'top_genres', 'last_updated')
        

class UserLocationSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for UserLocation model
    """
    class Meta:
        model = UserLocation
        geo_field = 'location'
        fields = ('id', 'user', 'timestamp')
        
        
# New serializers for vector data

class BuildingSerializer(GeoFeatureModelSerializer):
    """
    Serializer for Building model with GeoJSON support
    """
    height_meters = serializers.FloatField(source='height', read_only=True)
    level_count = serializers.IntegerField(source='levels', read_only=True)
    
    class Meta:
        model = Building
        geo_field = 'geometry'
        fields = ('id', 'osm_id', 'name', 'height_meters', 'level_count', 
                 'building_type', 'last_updated')
                 
    def to_representation(self, instance):
        """
        Override to add simplified geometry at lower zoom levels
        """
        # Get zoom level from context if provided
        zoom = self.context.get('zoom', 18)
        
        # For lower zoom levels, simplify the geometry
        if zoom < 16 and hasattr(instance, 'geometry'):
            # Simplify with more tolerance at lower zooms
            tolerance = 0.0001 if zoom < 14 else 0.00005
            instance.geometry = instance.geometry.simplify(tolerance, preserve_topology=True)
            
        return super().to_representation(instance)


class RoadSerializer(GeoFeatureModelSerializer):
    """
    Serializer for Road model with GeoJSON support
    """
    width_meters = serializers.FloatField(source='width', read_only=True)
    lane_count = serializers.IntegerField(source='lanes', read_only=True)
    
    class Meta:
        model = Road
        geo_field = 'geometry'
        fields = ('id', 'osm_id', 'name', 'road_type', 'width_meters', 
                 'lane_count', 'last_updated')
                 
    def to_representation(self, instance):
        zoom = self.context.get('zoom', 18)
        
        if zoom < 16 and hasattr(instance, 'geometry'):
            tolerance = 0.0001 if zoom < 14 else 0.00005
            instance.geometry = instance.geometry.simplify(tolerance, preserve_topology=True)
            
        return super().to_representation(instance)


class ParkSerializer(GeoFeatureModelSerializer):
    """
    Serializer for Park model with GeoJSON support
    """
    class Meta:
        model = Park
        geo_field = 'geometry'
        fields = ('id', 'osm_id', 'name', 'park_type', 'last_updated')
                 
    def to_representation(self, instance):
        zoom = self.context.get('zoom', 18)
        
        if zoom < 16 and hasattr(instance, 'geometry'):
            tolerance = 0.0001 if zoom < 14 else 0.00005
            instance.geometry = instance.geometry.simplify(tolerance, preserve_topology=True)
            
        return super().to_representation(instance)


class CachedRegionSerializer(GeoFeatureModelSerializer):
    """
    Serializer for CachedRegion model with GeoJSON support
    """
    size_mb = serializers.SerializerMethodField()
    bundle_url = serializers.SerializerMethodField()
    
    class Meta:
        model = CachedRegion
        geo_field = 'bounds'
        fields = ('id', 'name', 'north', 'south', 'east', 'west',
                 'min_zoom', 'max_zoom', 'created_at', 'last_accessed',
                 'access_count', 'size_mb', 'bundle_url')
                 
    def get_size_mb(self, obj):
        return round(obj.size_kb / 1024, 2)
        
    def get_bundle_url(self, obj):
        request = self.context.get('request')
        if request and obj.bundle_file:
            return request.build_absolute_uri(obj.bundle_file.url)
        return None


class UserMapSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for UserMapSettings model
    """
    username = serializers.SerializerMethodField()
    
    class Meta:
        model = UserMapSettings
        fields = ('id', 'user', 'username', 'show_feature_info', 'use_3d_buildings',
                 'default_latitude', 'default_longitude', 'default_zoom',
                 'max_cache_size_mb', 'theme', 'updated_at')
        read_only_fields = ('id', 'user', 'username', 'updated_at')
        
    def get_username(self, obj):
        return obj.user.username 