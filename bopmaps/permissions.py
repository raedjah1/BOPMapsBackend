from rest_framework import permissions
import logging

logger = logging.getLogger('bopmaps')

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    owner_field = 'owner'  # Default owner field name
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Write permissions are only allowed to the owner
        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            logger.warning(f"Owner field '{self.owner_field}' not found on {obj.__class__.__name__}")
            return False
            
        return owner == request.user


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to access it.
    """
    owner_field = 'owner'  # Default owner field name
    
    def has_object_permission(self, request, view, obj):
        # Permissions are only allowed to the owner
        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            logger.warning(f"Owner field '{self.owner_field}' not found on {obj.__class__.__name__}")
            return False
            
        return owner == request.user


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or staff users to access it.
    """
    owner_field = 'owner'  # Default owner field name
    
    def has_object_permission(self, request, view, obj):
        # Staff can do anything
        if request.user and request.user.is_staff:
            return True
            
        # Permissions are only allowed to the owner
        owner = getattr(obj, self.owner_field, None)
        if owner is None:
            logger.warning(f"Owner field '{self.owner_field}' not found on {obj.__class__.__name__}")
            return False
            
        return owner == request.user


class IsAdminUser(permissions.BasePermission):
    """
    Allows access only to admin users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff)


class IsActive(permissions.BasePermission):
    """
    Allows access only to active users.
    """
    message = "Your account is inactive or has been banned."
    
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active)


class IsNotBanned(permissions.BasePermission):
    """
    Denies access to banned users.
    """
    message = "Your account has been banned."
    
    def has_permission(self, request, view):
        if not hasattr(request.user, 'is_banned'):
            return True
        return not request.user.is_banned 