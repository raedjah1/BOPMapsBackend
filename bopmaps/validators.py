from django.core.validators import RegexValidator, MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.utils.deconstruct import deconstructible
import json
import re

# Username validator
username_validator = RegexValidator(
    regex=r'^[\w.@+-]+$',
    message=(
        'Enter a valid username. This value may contain only letters, '
        'numbers, and @/./+/-/_ characters.'
    ),
)

# JSON structure validator
@deconstructible
class JSONSchemaValidator:
    """
    Validator that ensures a JSON field matches a specific schema.
    """
    def __init__(self, schema):
        self.schema = schema
        
    def __call__(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValidationError("Invalid JSON format.")
        
        # Validate required fields
        for field, field_type in self.schema.items():
            if field not in value:
                raise ValidationError(f"Missing required field: '{field}'")
            
            # Check field type
            if field_type == 'string' and not isinstance(value[field], str):
                raise ValidationError(f"Field '{field}' must be a string.")
            elif field_type == 'number' and not isinstance(value[field], (int, float)):
                raise ValidationError(f"Field '{field}' must be a number.")
            elif field_type == 'boolean' and not isinstance(value[field], bool):
                raise ValidationError(f"Field '{field}' must be a boolean.")
            elif field_type == 'array' and not isinstance(value[field], list):
                raise ValidationError(f"Field '{field}' must be an array.")
            elif field_type == 'object' and not isinstance(value[field], dict):
                raise ValidationError(f"Field '{field}' must be an object.")


# Image dimension validator
@deconstructible
class ImageDimensionsValidator:
    """
    Validator that ensures uploaded images have certain dimensions.
    """
    def __init__(self, min_width=None, min_height=None, max_width=None, max_height=None):
        self.min_width = min_width
        self.min_height = min_height
        self.max_width = max_width
        self.max_height = max_height
        
    def __call__(self, value):
        if not value:
            return
            
        width, height = get_image_dimensions(value)
        
        if self.min_width and width < self.min_width:
            raise ValidationError(f"Image width must be at least {self.min_width}px. Current width: {width}px")
            
        if self.min_height and height < self.min_height:
            raise ValidationError(f"Image height must be at least {self.min_height}px. Current height: {height}px")
            
        if self.max_width and width > self.max_width:
            raise ValidationError(f"Image width must be at most {self.max_width}px. Current width: {width}px")
            
        if self.max_height and height > self.max_height:
            raise ValidationError(f"Image height must be at most {self.max_height}px. Current height: {height}px")


# URL validator for music services
@deconstructible
class MusicURLValidator:
    """
    Validator that ensures URLs match specific patterns for music services.
    """
    def __init__(self, service=None):
        self.service = service
        
    def __call__(self, value):
        if not value:
            return
            
        # Spotify track URL pattern
        spotify_pattern = r'^https?:\/\/(?:open\.)?spotify\.com\/track\/[a-zA-Z0-9]+(?:\?.*)?$'
        
        # Apple Music track URL pattern
        apple_pattern = r'^https?:\/\/music\.apple\.com\/[a-z]{2}\/album\/[^\/]+\/[0-9]+\?i=[0-9]+(?:\&.*)?$'
        
        # SoundCloud track URL pattern
        soundcloud_pattern = r'^https?:\/\/(?:www\.)?soundcloud\.com\/[^\/]+\/[^\/]+(?:\?.*)?$'
        
        if self.service == 'spotify' and not re.match(spotify_pattern, value):
            raise ValidationError("Invalid Spotify track URL. URL should be in the format: https://open.spotify.com/track/...")
            
        elif self.service == 'apple' and not re.match(apple_pattern, value):
            raise ValidationError("Invalid Apple Music track URL. URL should be in the format: https://music.apple.com/...")
            
        elif self.service == 'soundcloud' and not re.match(soundcloud_pattern, value):
            raise ValidationError("Invalid SoundCloud track URL. URL should be in the format: https://soundcloud.com/...")
            
        elif self.service is None:
            # If no specific service is specified, try all patterns
            if not (re.match(spotify_pattern, value) or re.match(apple_pattern, value) or re.match(soundcloud_pattern, value)):
                raise ValidationError("Invalid music service URL. URL should be from Spotify, Apple Music, or SoundCloud.")


# File size validator
@deconstructible
class FileSizeValidator:
    """
    Validator that ensures uploaded files don't exceed a maximum size.
    """
    def __init__(self, max_size_mb):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
    def __call__(self, value):
        if value.size > self.max_size_bytes:
            raise ValidationError(f"File size exceeds the maximum allowed: {self.max_size_bytes / (1024 * 1024):.1f} MB") 