from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from .permissions import IsOwnerOrReadOnly, IsOwner
from django.utils import timezone
from django.db import transaction
import logging
from django.views.generic import TemplateView

logger = logging.getLogger('bopmaps')

class IndexView(TemplateView):
    """Landing page for BOPMaps demo"""
    template_name = 'index.html'

class BaseModelViewSet(viewsets.ModelViewSet):
    """
    Base viewset that implements common functionality and error handling.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    
    def get_queryset(self):
        """
        Filter queryset based on request parameters.
        """
        queryset = super().get_queryset()
        
        # Add request to logging context
        logger.info(f"Fetching {self.queryset.model.__name__} objects for {self.request.user}")
        
        return queryset
        
    def perform_create(self, serializer):
        """
        Set the owner when creating an object.
        """
        try:
            with transaction.atomic():
                serializer.save(owner=self.request.user)
                logger.info(f"Created {serializer.Meta.model.__name__} object for {self.request.user}")
        except Exception as e:
            logger.error(f"Error creating {serializer.Meta.model.__name__}: {str(e)}")
            raise
    
    def perform_update(self, serializer):
        """
        Update an object with transaction and logging.
        """
        try:
            with transaction.atomic():
                serializer.save()
                logger.info(f"Updated {serializer.Meta.model.__name__} object: {serializer.instance.pk}")
        except Exception as e:
            logger.error(f"Error updating {serializer.Meta.model.__name__}: {str(e)}")
            raise
    
    def perform_destroy(self, instance):
        """
        Delete an object with transaction and logging.
        """
        try:
            with transaction.atomic():
                result = super().perform_destroy(instance)
                logger.info(f"Deleted {instance.__class__.__name__} object: {instance.pk}")
                return result
        except Exception as e:
            logger.error(f"Error deleting {instance.__class__.__name__}: {str(e)}")
            raise

    def get_serializer_context(self):
        """
        Add request to serializer context
        """
        context = super().get_serializer_context()
        # Additional context can be added here
        return context


class BaseReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Base viewset for read-only operations.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter queryset based on request parameters.
        """
        queryset = super().get_queryset()
        
        # Add request to logging context
        logger.info(f"Fetching {self.queryset.model.__name__} objects for {self.request.user}")
        
        return queryset


class OwnerModelViewSet(BaseModelViewSet):
    """
    Base viewset for resources that should only be visible to their owners.
    """
    permission_classes = [IsAuthenticated, IsOwner]
    
    def get_queryset(self):
        """
        Restrict queryset to objects owned by current user.
        """
        queryset = super().get_queryset()
        
        # By default, filter to show only current user's objects
        if hasattr(self.queryset.model, 'owner'):
            return queryset.filter(owner=self.request.user)
        
        logger.warning(f"Model {self.queryset.model.__name__} has no owner field")
        return queryset


class SoftDeleteModelViewSet(BaseModelViewSet):
    """
    Viewset that implements soft delete functionality.
    Objects are marked as inactive rather than being deleted.
    """
    def perform_destroy(self, instance):
        """
        Soft delete by setting is_active=False.
        """
        try:
            with transaction.atomic():
                instance.is_active = False
                instance.deleted_at = timezone.now()
                instance.save(update_fields=['is_active', 'deleted_at'])
                logger.info(f"Soft deleted {instance.__class__.__name__} object: {instance.pk}")
        except Exception as e:
            logger.error(f"Error soft deleting {instance.__class__.__name__}: {str(e)}")
            raise
    
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """
        Restore a soft-deleted object.
        """
        instance = self.get_object()
        
        try:
            with transaction.atomic():
                instance.is_active = True
                instance.deleted_at = None
                instance.save(update_fields=['is_active', 'deleted_at'])
                logger.info(f"Restored {instance.__class__.__name__} object: {instance.pk}")
                
                serializer = self.get_serializer(instance)
                return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error restoring {instance.__class__.__name__}: {str(e)}")
            return Response(
                {'error': f'Error restoring object: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class LoggingMixin:
    """
    Mixin to add standardized logging to any view.
    """
    def dispatch(self, request, *args, **kwargs):
        logger.info(f"{request.method} request to {request.path} from {request.user}")
        return super().dispatch(request, *args, **kwargs) 