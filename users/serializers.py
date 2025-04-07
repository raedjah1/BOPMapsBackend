from rest_framework import serializers
from django.contrib.auth import get_user_model
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from bopmaps.serializers import BaseSerializer, BaseReadOnlySerializer
import logging

logger = logging.getLogger('bopmaps')
User = get_user_model()

class UserSerializer(BaseSerializer):
    """
    Serializer for the User model
    """
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'profile_pic', 'bio', 
            'location', 'last_active', 'spotify_connected', 
            'apple_music_connected', 'soundcloud_connected',
        ]
        read_only_fields = ['id', 'last_active']
        
    def validate_username(self, value):
        """
        Validate that the username is unique (case insensitive).
        """
        if User.objects.filter(username__iexact=value).exclude(id=getattr(self.instance, 'id', None)).exists():
            raise ValidationError("A user with this username already exists.")
        return value


class UserGeoSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON serializer for User model
    """
    class Meta:
        model = User
        geo_field = 'location'
        fields = ['id', 'username', 'profile_pic', 'last_active']


class UserRegistrationSerializer(BaseSerializer):
    """
    Serializer for registering new users
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = [
            'username', 'email', 'password', 'password_confirm', 
            'profile_pic', 'bio'
        ]
    
    def validate_email(self, value):
        """
        Validate that the email is unique (case insensitive).
        """
        if User.objects.filter(email__iexact=value).exists():
            raise ValidationError("A user with this email already exists.")
        return value.lower()  # Normalize to lowercase
    
    def validate_password(self, value):
        """
        Validate password using Django's password validators.
        """
        try:
            validate_password(value)
        except ValidationError as e:
            logger.warning(f"Password validation failed: {e}")
            raise serializers.ValidationError(e.messages)
        return value
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password": "Password fields don't match."})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        try:
            user = User(**validated_data)
            user.set_password(password)
            user.save()
            logger.info(f"User created: {user.username}")
            return user
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise


class UserUpdateSerializer(BaseSerializer):
    """
    Serializer for updating user profile
    """
    current_password = serializers.CharField(
        write_only=True, required=False, style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        write_only=True, required=False, style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'profile_pic', 'bio', 'location',
            'current_password', 'new_password'
        ]
        read_only_fields = ['email']  # Email can't be updated
        
    def validate(self, data):
        # If updating password, current_password is required
        if 'new_password' in data and not data.get('current_password'):
            raise serializers.ValidationError(
                {"current_password": "Current password is required to set a new password."}
            )
            
        # If both password fields are provided, validate current password
        if 'current_password' in data and 'new_password' in data:
            if not self.instance.check_password(data['current_password']):
                raise serializers.ValidationError(
                    {"current_password": "Current password is not correct."}
                )
                
            # Validate new password with Django's built-in validators
            try:
                validate_password(data['new_password'], self.instance)
            except ValidationError as e:
                raise serializers.ValidationError({"new_password": e.messages})
                
        return data
    
    def update(self, instance, validated_data):
        # Handle password update separately
        current_password = validated_data.pop('current_password', None)
        new_password = validated_data.pop('new_password', None)
        
        # Update the instance with the validated data
        instance = super().update(instance, validated_data)
        
        # Update password if provided
        if current_password and new_password:
            instance.set_password(new_password)
            instance.save()
            logger.info(f"Password updated for user: {instance.username}")
            
        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for password reset request
    """
    email = serializers.EmailField()
    
    def validate_email(self, value):
        # Convert to lowercase for normalization
        return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for password reset confirmation
    """
    token = serializers.CharField()
    password = serializers.CharField(style={'input_type': 'password'})
    
    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value 