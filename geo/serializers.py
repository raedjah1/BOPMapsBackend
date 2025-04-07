from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import TrendingArea, UserLocation
from bopmaps.serializers import BaseSerializer

class TrendingAreaSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for TrendingArea model
    """
    class Meta:
        model = TrendingArea
        geo_field = 'center'
        fields = ['id', 'name', 'center', 'radius', 'pin_count', 'top_genres', 'last_updated']
        

class UserLocationSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for UserLocation model
    """
    class Meta:
        model = UserLocation
        geo_field = 'location'
        fields = ['id', 'user', 'location', 'timestamp'] 