from rest_framework import serializers
from .models import PinSkin, Achievement, UserAchievement
from bopmaps.serializers import BaseSerializer, BaseReadOnlySerializer, TimeStampedModelSerializer
import logging

logger = logging.getLogger('bopmaps')

class PinSkinSerializer(TimeStampedModelSerializer):
    """
    Serializer for the PinSkin model
    """
    is_owned = serializers.SerializerMethodField()
    
    class Meta(TimeStampedModelSerializer.Meta):
        model = PinSkin
        fields = ['id', 'name', 'image', 'description', 'is_premium', 'created_at', 'is_owned']
        
    def get_is_owned(self, obj):
        """
        Check if the current user owns this skin.
        """
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return False
            
        # If user hasn't unlocked this premium skin yet
        if obj.is_premium:
            # Check if user has completed an achievement that rewards this skin
            return Achievement.objects.filter(
                reward_skin=obj,
                completions__user=user
            ).exists()
            
        # Non-premium skins are available to everyone
        return True


class AchievementSerializer(BaseSerializer):
    """
    Serializer for the Achievement model
    """
    reward_skin_details = PinSkinSerializer(source='reward_skin', read_only=True)
    is_completed = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    
    class Meta:
        model = Achievement
        fields = [
            'id', 'name', 'description', 'icon', 'criteria',
            'reward_skin', 'reward_skin_details', 'is_completed',
            'progress'
        ]
        read_only_fields = ['id', 'is_completed', 'progress']
        
    def get_is_completed(self, obj):
        """
        Check if the current user has completed this achievement.
        """
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return False
            
        return UserAchievement.objects.filter(
            user=user, 
            achievement=obj
        ).exists()
        
    def get_progress(self, obj):
        """
        Get the current user's progress towards this achievement.
        """
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return {}
            
        try:
            user_achievement = UserAchievement.objects.get(
                user=user, 
                achievement=obj
            )
            return user_achievement.progress
        except UserAchievement.DoesNotExist:
            return {}


class UserAchievementSerializer(TimeStampedModelSerializer):
    """
    Serializer for the UserAchievement model
    """
    achievement = AchievementSerializer(read_only=True)
    
    class Meta(TimeStampedModelSerializer.Meta):
        model = UserAchievement
        fields = ['id', 'user', 'achievement', 'completed_at', 'progress', 'created_at']
        read_only_fields = ['id', 'user', 'completed_at'] 