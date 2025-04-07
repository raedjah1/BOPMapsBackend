from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Pin, PinInteraction
from users.serializers import UserSerializer
from gamification.serializers import PinSkinSerializer
from bopmaps.serializers import BaseSerializer, TimeStampedModelSerializer
from bopmaps.validators import MusicURLValidator
from django.utils import timezone
import logging

logger = logging.getLogger('bopmaps')

class PinSerializer(TimeStampedModelSerializer):
    """
    Serializer for Pin model
    """
    owner = UserSerializer(read_only=True)
    skin_details = PinSkinSerializer(source='skin', read_only=True)
    interaction_count = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()
    has_expired = serializers.SerializerMethodField()
    
    class Meta(TimeStampedModelSerializer.Meta):
        model = Pin
        fields = [
            'id', 'owner', 'location', 'title', 'description',
            'track_title', 'track_artist', 'album', 'track_url',
            'service', 'skin', 'skin_details', 'rarity', 'aura_radius',
            'is_private', 'expiration_date', 'created_at', 'updated_at',
            'interaction_count', 'distance', 'has_expired'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner', 'skin_details', 'distance', 'has_expired']
        extra_kwargs = {
            'track_url': {'validators': [MusicURLValidator()]},
            'expiration_date': {'required': False, 'allow_null': True},
        }
    
    def get_interaction_count(self, obj):
        """Get count of different interactions for this pin"""
        counts = {}
        for interaction_type, _ in PinInteraction.INTERACTION_TYPES:
            counts[interaction_type] = obj.interactions.filter(
                interaction_type=interaction_type
            ).count()
        return counts
    
    def get_distance(self, obj):
        """Get distance if annotated by the query"""
        if hasattr(obj, 'distance'):
            # Convert to meters
            return float(obj.distance.m)
        return None
    
    def get_has_expired(self, obj):
        """Check if pin has expired"""
        if obj.expiration_date:
            return obj.expiration_date < timezone.now()
        return False
    
    def validate(self, data):
        """
        Validate the pin data.
        - Ensure the track_url matches the service type
        - Ensure aura_radius is within limits
        """
        service = data.get('service')
        track_url = data.get('track_url')
        
        if service and track_url:
            # Use our service-specific validator
            validator = MusicURLValidator(service=service)
            try:
                validator(track_url)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({'track_url': e.detail})
                
        # Validate aura_radius limits
        aura_radius = data.get('aura_radius')
        if aura_radius is not None:
            if aura_radius < 10:
                raise serializers.ValidationError({'aura_radius': 'Aura radius must be at least 10 meters.'})
            elif aura_radius > 1000:
                raise serializers.ValidationError({'aura_radius': 'Aura radius cannot exceed 1000 meters.'})
                
        return data
        
    def create(self, validated_data):
        """Ensure owner is set to request user when creating a pin"""
        validated_data['owner'] = self.context.get('request').user
        
        try:
            instance = super().create(validated_data)
            logger.info(f"Pin created by {instance.owner.username}: {instance.title}")
            return instance
        except Exception as e:
            logger.error(f"Error creating pin: {str(e)}")
            raise


class PinGeoSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for Pin model to display on map
    """
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    like_count = serializers.SerializerMethodField()
    collect_count = serializers.SerializerMethodField()
    distance = serializers.SerializerMethodField()
    has_expired = serializers.SerializerMethodField()
    
    class Meta:
        model = Pin
        geo_field = 'location'
        fields = [
            'id', 'owner_name', 'title', 'track_title', 
            'track_artist', 'service', 'rarity', 'like_count',
            'collect_count', 'created_at', 'distance', 'has_expired',
            'aura_radius'
        ]
    
    def get_like_count(self, obj):
        return obj.interactions.filter(interaction_type='like').count()
    
    def get_collect_count(self, obj):
        return obj.interactions.filter(interaction_type='collect').count()
        
    def get_distance(self, obj):
        """Get distance if annotated by the query"""
        if hasattr(obj, 'distance'):
            # Convert to meters
            return float(obj.distance.m)
        return None
    
    def get_has_expired(self, obj):
        """Check if pin has expired"""
        if obj.expiration_date:
            return obj.expiration_date < timezone.now()
        return False


class PinInteractionSerializer(BaseSerializer):
    """
    Serializer for PinInteraction model
    """
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = PinInteraction
        fields = ['id', 'user', 'pin', 'interaction_type', 'created_at']
        read_only_fields = ['id', 'created_at', 'user']
    
    def create(self, validated_data):
        """Ensure user is set to request user when creating an interaction"""
        validated_data['user'] = self.context.get('request').user
        
        try:
            instance = super().create(validated_data)
            logger.info(f"Pin interaction: {instance.user.username} {instance.interaction_type} pin {instance.pin.id}")
            return instance
        except Exception as e:
            logger.error(f"Error creating pin interaction: {str(e)}")
            raise 