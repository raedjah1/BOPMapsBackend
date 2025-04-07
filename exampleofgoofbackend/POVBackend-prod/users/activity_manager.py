from users.notifications import send_fcm_notification, send_fcm_notification_to_multiple_users
from .models import ActivityEvent, UserActivity, ActivityItem
from firebase_admin import messaging
import firebase_admin
from firebase_admin import credentials

class ActivityManager:
    @staticmethod
    def create_activity_event(actor, action_type, target_id, target_type):
        event = ActivityEvent.objects.create(
            actor=actor,
            action_type=action_type,
            target_id=target_id,
            target_type=target_type
        )
        return event

    @staticmethod
    def create_user_activity(user, event):
        UserActivity.objects.create(user=user, event=event)

    @staticmethod
    def create_activity_item(creator, text, user, image_url=None):
        ActivityItem.objects.create(
            creator=creator,
            text=text,
            user=user,
            image_url=image_url
        )

    @staticmethod
    def send_push_notification(user, title, body):
        return send_fcm_notification(user, title, body)

    @staticmethod
    def send_batch_push_notifications(users, title, body):
        """
        Send push notifications to multiple users in batches.
        
        Args:
            users: List of User objects
            title: Notification title
            body: Notification body
            
        Returns:
            tuple: (success_count, failure_count)
        """
        return send_fcm_notification_to_multiple_users(users, title, body)

    @classmethod
    def create_activity_and_notify(cls, actor, action_type, target_id, target_type, notify_user, notification_title, notification_body):
        event = cls.create_activity_event(actor, action_type, target_id, target_type)
        cls.create_user_activity(notify_user, event)
        cls.send_push_notification(notify_user, notification_title, notification_body)
