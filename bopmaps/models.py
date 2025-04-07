from django.db import models
import uuid
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger('bopmaps')

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    created_at and updated_at fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    An abstract base class model that uses UUID as its primary key.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class SoftDeleteModelMixin(models.Model):
    """
    An abstract base class model that provides soft delete functionality.
    Objects are marked as inactive rather than being deleted from the database.
    """
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        """
        Soft delete the object by setting is_active=False and deleted_at=timezone.now()
        """
        hard_delete = kwargs.pop('hard_delete', False)
        
        if hard_delete:
            # Actually delete the object from the database
            return super().delete(*args, **kwargs)
            
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_active', 'deleted_at'])

    def restore(self):
        """
        Restore a soft-deleted object
        """
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=['is_active', 'deleted_at'])


class SoftDeleteManager(models.Manager):
    """
    Manager for models with SoftDeleteModelMixin that filters out soft-deleted objects by default.
    """
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def with_deleted(self):
        """
        Return a queryset including soft-deleted objects
        """
        return super().get_queryset()

    def deleted(self):
        """
        Return a queryset of only soft-deleted objects
        """
        return super().get_queryset().filter(is_active=False)


class ValidationModelMixin(models.Model):
    """
    Mixin that logs validation errors.
    """
    class Meta:
        abstract = True
        
    def full_clean(self, *args, **kwargs):
        try:
            return super().full_clean(*args, **kwargs)
        except ValidationError as e:
            logger.warning(
                f"Validation error on {self.__class__.__name__} (id={getattr(self, 'id', 'new')}): {e}"
            )
            raise 