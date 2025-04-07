from rest_framework import serializers
import logging

logger = logging.getLogger('bopmaps')

class BaseSerializer(serializers.ModelSerializer):
    """
    Base serializer with improved error handling.
    This serializer provides custom validation error messages 
    and logs validation errors for debugging.
    """
    
    def is_valid(self, raise_exception=False):
        """
        Enhanced validation method that logs validation errors
        """
        valid = super().is_valid(raise_exception=False)
        
        if not valid and self.errors:
            logger.warning(
                f"Validation failed for {self.__class__.__name__}: {self.errors}"
            )
            
        if not valid and raise_exception:
            raise serializers.ValidationError(self.errors)
            
        return valid
    
    def to_representation(self, instance):
        """
        Enhanced representation method with error handling
        """
        try:
            return super().to_representation(instance)
        except Exception as e:
            logger.error(
                f"Error in {self.__class__.__name__}.to_representation: {str(e)}"
            )
            raise


class BaseReadOnlySerializer(serializers.ModelSerializer):
    """
    Base serializer for read-only operations.
    Use this for serializers that will only be used for GET requests
    to improve performance.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.Meta.read_only_fields = [field.name for field in self.Meta.model._meta.fields]


class TimeStampedModelSerializer(BaseSerializer):
    """
    Base serializer for models with created_at and updated_at fields.
    """
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    
    class Meta:
        fields = ['created_at', 'updated_at']


def serialize_user_for_response(user, request=None):
    """
    Standardized way to serialize user info for API responses.
    
    Args:
        user: The user object to serialize
        request: Optional request object for context
        
    Returns:
        Dictionary with standard user info
    """
    from users.serializers import UserSerializer
    
    context = {'request': request} if request else {}
    serializer = UserSerializer(user, context=context)
    return serializer.data 