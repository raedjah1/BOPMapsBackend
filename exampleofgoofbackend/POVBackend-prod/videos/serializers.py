# videos/serializers.py
from rest_framework import serializers
from .models import Invite, Vision, Comment, StoryNode, StoryOption
from users.models import Interest, Spectator, User
from users.serializers import UserSerializer, CreatorSerializer
from .models import Poll, PollItem, Vote

class StoryOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryOption
        fields = ['id', 'text', 'video_url', 'is_local_video', 'next_node']

class StoryNodeSerializer(serializers.ModelSerializer):
    options = StoryOptionSerializer(many=True, read_only=True, source='options.all')
    
    class Meta:
        model = StoryNode
        fields = ['id', 'video_url', 'is_local_video', 'question', 'options']

class VisionSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        field_names = kwargs.pop('field_names', None)
        super().__init__(*args, **kwargs)
        
        if field_names:
            allowed = set(field_names)
            existing = set(self.fields)
            for field_name in existing - allowed:
                self.fields.pop(field_name)
        
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                spectator = Spectator.objects.get(user_id=request.user.pk)
                self._spectator = spectator
                self._liked_vision_ids = set(spectator.liked_visions.values_list('pk', flat=True))
                self._disliked_vision_ids = set(spectator.disliked_visions.values_list('pk', flat=True))
                self._subscriptions = set(spectator.subscriptions.all())
            except Spectator.DoesNotExist:
                self._spectator = None
                self._liked_vision_ids = set()
                self._disliked_vision_ids = set()
                self._subscriptions = set()
                
    interests = serializers.SlugRelatedField(slug_field='name', queryset=Interest.objects.all(), many=True)
    thumbnail = serializers.CharField(max_length=500, required=False)
    url = serializers.CharField(max_length=500, required=False)
    creator = serializers.SerializerMethodField()
    aspect_ratio = serializers.CharField(max_length=4, required=False)
    is_locked = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    is_interactive = serializers.BooleanField(read_only=True)
    story_nodes = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_disliked = serializers.SerializerMethodField()
    watched_at = serializers.SerializerMethodField()
    camera_type = serializers.CharField(read_only=True)
    quality = serializers.CharField(read_only=True)
    comment_count = serializers.SerializerMethodField()
    access_type = serializers.CharField(read_only=True)
    ppv_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_highlight = serializers.BooleanField(read_only=True)
    tips_received = serializers.SerializerMethodField()
    tip_count = serializers.SerializerMethodField()
    
    class Meta: 
        model = Vision
        fields = ['pk', 'title', 'thumbnail', 'description', 'views', 'url', 'creator', 
                  'likes', 'dislikes', 'interests', 'live', 'aspect_ratio', 'created_at', 'stereo_mapping', 
                  'is_locked', 'status', 'is_interactive', 'story_nodes', 'is_liked', 'is_disliked', 'watched_at',
                  'camera_type', 'quality', 'comment_count', 'access_type', 'ppv_price', 'is_highlight',
                  'tips_received', 'tip_count', 'duration']
        read_only_fields = ['creator', 'likes', 'dislikes', 'created_at', 'is_locked']

    def get_creator(self, obj):
        return CreatorSerializer(obj.creator).data
    
    def get_is_liked(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'is_liked_db'):
            return obj.is_liked_db
            
        # Fall back to original logic
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                spectator = Spectator.objects.get(user_id=request.user.pk)
                return obj.pk in spectator.liked_visions.values_list('pk', flat=True)
            except Spectator.DoesNotExist:
                return False
        return False

    def get_is_disliked(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'is_disliked_db'):
            return obj.is_disliked_db
            
        # Fall back to original logic
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                spectator = Spectator.objects.get(user_id=request.user.pk)
                return obj.pk in spectator.disliked_visions.values_list('pk', flat=True)
            except Spectator.DoesNotExist:
                return False
        return False

    def get_watched_at(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'watched_at_db'):
            return obj.watched_at_db
            
        # Fall back to original logic
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            try:
                watch_history = obj.watchhistory_set.get(user=request.user)
                return watch_history.watched_at
            except:
                return None
        return None
    
    def get_comment_count(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'comment_count_db'):
            return obj.comment_count_db
        # Fall back to original logic
        return getattr(obj, 'comment_count', obj.comment.count())

    def get_is_locked(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'is_locked_db'):
            return obj.is_locked_db
        
        # Use original annotation if available
        if hasattr(obj, 'is_locked'):
            return obj.is_locked
            
        # Fall back to original logic
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return obj.access_type == 'premium'
        try:
            spectator = Spectator.objects.get(user_id=request.user.pk)
            is_subscribed = obj.creator in spectator.subscriptions.all()
            is_ppv_purchased = spectator.ppv_visions.filter(pk=obj.pk).exists()
            # Vision is locked if it's premium AND user is not subscribed AND user has not purchased it as PPV
            return obj.access_type == 'premium' and not is_subscribed and not is_ppv_purchased
        except Spectator.DoesNotExist:
            return obj.access_type == 'premium'

    def get_story_nodes(self, obj):
        if obj.story_graph and 'nodes' in obj.story_graph:
            return obj.story_graph['nodes']
        return []

    def get_tips_received(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'total_tips_received'):
            return obj.total_tips_received
        # Fall back to property method
        return float(obj.tips_received)
    
    def get_tip_count(self, obj):
        # Use DB annotation if available
        if hasattr(obj, 'tip_count'):
            return obj.tip_count
        # Fall back to counting related tips
        return obj.tips.count()

class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(required=False)
    vision = serializers.PrimaryKeyRelatedField(queryset=Vision.objects.all())
    initial_comment = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.all(), required=False, allow_null=True)
    reply_user = serializers.SlugRelatedField(slug_field='username', queryset=User.objects.all(), required=False, allow_null=True)
    isLikedByUser = serializers.SerializerMethodField()
    likesCount = serializers.SerializerMethodField()
    is_reply = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()

    class Meta: 
        model = Comment
        fields = ['pk', 'user', 'likesCount', 'vision', 'initial_comment', 'text', 'reply_user', 'created_at', 'isLikedByUser', 'is_reply', 'replies_count']
        read_only_fields = ['user', 'created_at']

    def get_isLikedByUser(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return request.user in obj.likes.all()
        return False
    
    def get_likesCount(self, obj):
        return obj.likes.count()

    def get_is_reply(self, obj):
        return obj.parent_comment is not None

    def get_replies_count(self, obj):
        return Comment.objects.filter(parent_comment=obj).count()

class PollItemSerializer(serializers.ModelSerializer):
    percentage = serializers.FloatField(read_only=True)
    selected = serializers.SerializerMethodField()

    class Meta:
        model = PollItem
        fields = ['id', 'text', 'votes', 'percentage', 'selected']

    def get_selected(self, obj):
        user = self.context['request'].user
        return Vote.objects.filter(poll_item=obj, user=user).exists()

class PollSerializer(serializers.ModelSerializer):
    items = PollItemSerializer(many=True, read_only=True)
    total_votes = serializers.IntegerField(read_only=True)

    class Meta:
        model = Poll
        fields = ['id', 'question', 'items', 'total_votes', 'created_at', 'ends_at', 'is_active']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        items = representation['items']
        total_votes = sum(item['votes'] for item in items)
        
        for item in items:
            item['percentage'] = (item['votes'] / total_votes * 100) if total_votes > 0 else 0

        representation['total_votes'] = total_votes
        return representation
    
class InviteSerializer(serializers.ModelSerializer):
    sender = serializers.SlugRelatedField(slug_field='username', read_only=True)
    creator = serializers.SlugRelatedField(slug_field='username', read_only=True)
    vision = serializers.PrimaryKeyRelatedField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Invite
        fields = ['id', 'sender', 'creator', 'vision', 'status', 'created_at', 'updated_at']
