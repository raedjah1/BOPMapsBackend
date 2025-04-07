from django.db import models
from users.models import Creator, Spectator
from videos.models import Vision
from datetime import timedelta
from django.utils import timezone
from .aws_utils import schedule_fcm_notification
from users.notifications import send_fcm_notification_to_multiple_users
import logging
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

logger = logging.getLogger(__name__)

class Event(models.Model):
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    description = models.TextField()
    vision = models.OneToOneField(Vision, on_delete=models.CASCADE, null=True, blank=True)
    start_time = models.DateTimeField()
    thumbnail = models.URLField(max_length=500, null=True)
    remind_me_list = models.ManyToManyField(Spectator, blank=True)
    notification_rule_arn = models.CharField(max_length=255, null=True, blank=True)

    # Add new fields for recommendation optimization
    feature_vector = models.BinaryField(null=True, blank=True)  # Store TF-IDF vector
    popularity_score = models.FloatField(default=0.0)  # Computed popularity score
    engagement_score = models.FloatField(default=0.0)  # Computed engagement score
    last_recommendation_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['start_time']),
            models.Index(fields=['popularity_score']),
            models.Index(fields=['engagement_score']),
            models.Index(fields=['creator', 'start_time']),
            models.Index(fields=['last_recommendation_update']),
            models.Index(fields=['-start_time']),
            models.Index(fields=['creator', '-engagement_score']),
            models.Index(fields=['creator', 'vision']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        # If new event, ensure vision is not live
        if is_new and self.vision:
            self.vision.live = False
            self.vision.save()
        
        super().save(*args, **kwargs)
        
        if is_new or 'start_time' in kwargs.get('update_fields', []):
            self._schedule_notifications()

    def _get_notification_recipients(self):
        """Get list of FCM tokens for all recipients."""
        tokens = []
        
        # Add creator's token if available and they have vision activity notifications enabled
        creator_user = self.creator.user
        if creator_user.fcm_token:
            tokens.append(creator_user.fcm_token)
        
        # Add spectators' tokens if they have subscription notifications enabled
        for spectator in self.remind_me_list.select_related('user').all():
            spectator_user = spectator.user
            if spectator_user.fcm_token and spectator_user.notify_subscriptions:
                tokens.append(spectator_user.fcm_token)
        
        logger.info(f"Notification recipients for event {self.id}: {len(tokens)} tokens")
        if not tokens:
            logger.warning(f"No valid FCM tokens found for event {self.id}. Creator token: {bool(creator_user.fcm_token)}, Spectators count: {self.remind_me_list.count()}")
        
        return tokens

    def _schedule_notifications(self):
        """Schedule notifications for all users in the remind_me_list and the creator."""
        try:
            # Schedule notifications 1 hour before event starts
            notification_time = self.start_time - timedelta(hours=1)
            
            # Only schedule if the notification time is in the future
            if notification_time > timezone.now():
                tokens = self._get_notification_recipients()

                if tokens:
                    notification_title = f"Event Reminder: {self.title}"
                    notification_body = f"Your event '{self.title}' is starting in 1 hour!"
                    
                    rule_arn = schedule_fcm_notification(
                        event_id=self.id,
                        fcm_tokens=tokens,
                        notification_time=notification_time,
                        title=notification_title,
                        body=notification_body,
                        update_existing=bool(self.notification_rule_arn),
                        existing_rule_arn=self.notification_rule_arn
                    )
                    
                    if rule_arn and not self.notification_rule_arn:
                        # Only save if this is a new rule
                        self.notification_rule_arn = rule_arn
                        self.save(update_fields=['notification_rule_arn'])
                    
                    logger.info(
                        f"{'Updated' if self.notification_rule_arn else 'Scheduled'} "
                        f"notifications for event {self.id} at {notification_time}"
                    )
        except Exception as e:
            logger.error(f"Error scheduling notifications for event {self.id}: {str(e)}")

@receiver(m2m_changed, sender=Event.remind_me_list.through)
def handle_remind_me_list_change(sender, instance, action, **kwargs):
    """Handle changes to the remind_me_list M2M relationship."""
    if action in ["post_add", "post_remove"]:
        # Re-schedule notifications with updated user list
        # This will update the existing rule with the new list of users
        instance._schedule_notifications()

class EventSimilarity(models.Model):
    """
    Stores precomputed similarity scores between events for fast recommendation lookups.
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='similarities')
    similar_event = models.ForeignKey(Event, on_delete=models.CASCADE)
    similarity_score = models.FloatField()  # Content-based similarity
    engagement_boost = models.FloatField(default=0.0)  # Boost based on user engagement
    final_score = models.FloatField()  # Combined similarity and engagement score
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('event', 'similar_event')
        indexes = [
            models.Index(fields=['event', '-final_score']),
            models.Index(fields=['similar_event', '-final_score']),
            models.Index(fields=['created_at'])
        ]

    def __str__(self):
        return f"Similarity between {self.event.title} and {self.similar_event.title}"

class EventAnnoyIndex(models.Model):
    """
    Stores the Annoy index binary data for fast event similarity lookups
    """
    index_binary = models.BinaryField()
    event_ids = models.JSONField()  # Store list of event IDs in index order
    vector_size = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['is_current'])
        ]
        
    def __str__(self):
        return f"Event Annoy Index (created: {self.created_at}, events: {len(self.event_ids)})"