from rest_framework import serializers
from .models import Friend
from users.serializers import UserMiniSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class FriendSerializer(serializers.ModelSerializer):
    """
    Serializer for Friend model (for accepted friendships)
    """
    friend = serializers.SerializerMethodField()
    
    class Meta:
        model = Friend
        fields = ['id', 'friend', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_friend(self, obj):
        """
        Return the other user in the friendship based on who is viewing
        """
        request_user = self.context.get('request').user
        if obj.requester == request_user:
            return UserMiniSerializer(obj.recipient).data
        else:
            return UserMiniSerializer(obj.requester).data


class FriendRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for Friend model that includes all fields
    """
    requester = UserMiniSerializer(read_only=True)
    recipient = UserMiniSerializer(read_only=True)
    recipient_id = serializers.PrimaryKeyRelatedField(
        write_only=True, 
        queryset=User.objects.all(),
        source='recipient'
    )
    
    class Meta:
        model = Friend
        fields = ['id', 'requester', 'recipient', 'recipient_id', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'requester', 'created_at', 'updated_at'] 

    def validate(self, attrs):
        request_user = self.context['request'].user
        recipient = attrs.get('recipient')

        if recipient == request_user:
            raise serializers.ValidationError("You cannot send a friend request to yourself.")

        # Check for existing pending or accepted requests in either direction
        if Friend.objects.filter(
            requester=request_user, recipient=recipient, status__in=['pending', 'accepted']
        ).exists() or Friend.objects.filter(
            requester=recipient, recipient=request_user, status__in=['pending', 'accepted']
        ).exists():
            raise serializers.ValidationError("A friend request already exists or you are already friends.")
            
        return attrs 