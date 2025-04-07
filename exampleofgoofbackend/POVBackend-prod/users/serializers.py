# users/serializers.py
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth.password_validation import validate_password

from subscriptions.models import Subscription
from .models import SignInCodeRequest, User, Interest, Spectator, Creator, Badge, UserBadge

class InterestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Interest
        fields = ['pk', 'name']
        read_only_fields = ['pk']

class UserSerializer(serializers.ModelSerializer):
    is_verified = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'profile_picture_url', 'cover_picture_url', 'is_spectator', 'is_creator', 'sign_in_method', 'is_verified', 'bio']

    def get_is_verified(self, obj):
        try:
            return obj.creator.is_verified
        except Creator.DoesNotExist:
            return False
        except Exception as e:
            print(e)
            return False

    def get_bio(self, obj):
        try:
            return obj.creator.bio
        except Creator.DoesNotExist:
            return ""
        except Exception as e:
            print(e)
            return ""

class RegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True, validators=[UniqueValidator(queryset=User.objects.all())])
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    
    class Meta: 
        model = User
        fields = ['username', 'first_name', 'email', 'last_name', 'password']

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'], 
            email=validated_data['email']
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

class CreatorSerializer(serializers.ModelSerializer):
    user = UserSerializer(required=False)
    is_subscribed = serializers.SerializerMethodField()
    subscription_end_date = serializers.SerializerMethodField()
    subscription_renewal_date = serializers.SerializerMethodField()
    subscription_type = serializers.SerializerMethodField()
    
    class Meta: 
        model = Creator
        fields = ['pk', 'user', 'subscription_price', 'subscriber_count', 'is_verified', 
                 'is_subscribed', 'subscription_end_date', 'subscription_renewal_date', 'subscription_type']
        read_only_fields = ['pk', 'user', 'subscriber_count']

    def get_is_subscribed(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        try:
            spectator = Spectator.objects.get(pk=request.user.pk)
            return spectator.subscriptions.filter(pk=obj.pk).exists()
        except:
            return False
            
    def get_subscription_end_date(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            spectator = Spectator.objects.get(pk=request.user.pk)
            subscription = spectator.subscription_set.get(creator=obj)
            return subscription.end_date
        except:
            return None
            
    def get_subscription_renewal_date(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            spectator = Spectator.objects.get(pk=request.user.pk)
            subscription = spectator.subscription_set.get(creator=obj)
            return subscription.next_payment_date
        except:
            return None
            
    def get_subscription_type(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            spectator = Spectator.objects.get(pk=request.user.pk)
            subscription = spectator.subscription_set.get(creator=obj)
            return subscription.subscription_type
        except:
            return None

class SpectatorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    interests = serializers.SlugRelatedField(slug_field='name', queryset=Interest.objects.all(), many=True)
    subscriptions = CreatorSerializer(required=False, many=True)
    is_premium = serializers.SerializerMethodField()
    
    class Meta: 
        model = Spectator
        fields = ['pk', 'user', 'subscriptions', 'interests', 'liked_visions', 'watch_later', 'liked_comments', 'watch_history', 'is_premium']
        read_only_fields = ['liked_visions', 'watch_later', 'liked_comments', 'watch_history']

    def get_is_premium(self, obj):
        creator = self.context.get('creator')
        if not creator:
            return False
        try:
            subscription = obj.subscription_set.get(creator=creator)
            return subscription.subscription_type == 'paid'
        except:
            return False

class SignInCodeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignInCodeRequest
        fields = ['id', 'user', 'status', 'code', 'created_at']
        read_only_fields = ['id', 'created_at']

class BadgeSerializer(serializers.ModelSerializer):
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Badge
        fields = ['id', 'name', 'description', 'image_url', 'badge_type', 'is_locked']

    def get_is_locked(self, obj):
        user = self.context['request'].user
        return not UserBadge.objects.filter(user=user, badge=obj).exists()

class UserBadgeSerializer(serializers.ModelSerializer):
    badge = BadgeSerializer()

    class Meta:
        model = UserBadge
        fields = ['id', 'badge', 'earned_date']