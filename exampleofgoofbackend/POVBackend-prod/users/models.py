# users/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.utils import timezone

User = get_user_model()

class User(User):
    profile_picture_url = models.CharField(
        max_length=400,
        default='https://res.cloudinary.com/pov/image/upload/v1667553173/defaultPic_s89yno.png'
    )
    cover_picture_url = models.CharField(
        max_length=400,
        default='https://res.cloudinary.com/pov/image/upload/v1667553173/defaultPic_s89yno.png'
    )
    is_spectator = models.BooleanField(default=False)
    is_creator = models.BooleanField(default=False)
    sign_in_method = models.CharField(
        max_length=10,
        choices=[
            ('apple', 'Apple'),
            ('google', 'Google'), 
            ('facebook', 'Facebook'),
            ('email', 'Email')
        ],
        default='email'
    )
    blocked_users = models.ManyToManyField('self', symmetrical=False, related_name='blocked_by')
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=32, blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=1,
        choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')],
        null=True,
        blank=True
    )
    country = models.CharField(max_length=255, null=True, blank=True)  # ISO country code
    fcm_token = models.CharField(max_length=255, blank=True, null=True)
    is_banned = models.BooleanField(default=False)
    ban_reason = models.TextField(blank=True, null=True)
    banned_at = models.DateTimeField(null=True, blank=True)
    banned_until = models.DateTimeField(null=True, blank=True)  # For temporary bans
    
    # RevenueCat integration
    revenuecat_uuid = models.CharField(max_length=100, blank=True, null=True, unique=True, 
                                      help_text='Unique identifier for this user in RevenueCat')
    
    # Notification settings
    notify_subscriptions = models.BooleanField(default=True, help_text='Notify about activity from subscribed channels')
    notify_recommended_visions = models.BooleanField(default=True, help_text='Notify about recommended visions')
    notify_comment_replies = models.BooleanField(default=True, help_text='Notify about replies to comments')
    notify_vision_activity = models.BooleanField(default=True, help_text='Notify about comments and other activity on visions')

    def __str__(self):
        return self.username

class Interest(models.Model):
    name = models.CharField(max_length=35, unique=True)

    def save(self, *args, **kwargs):
        self.name = self.name.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Spectator(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    subscriptions = models.ManyToManyField('Creator', blank=True, db_index=True)
    liked_visions = models.ManyToManyField('videos.Vision', blank=True, related_name='liked_by')
    disliked_visions = models.ManyToManyField('videos.Vision', blank=True, related_name='disliked_by')
    watch_later = models.ManyToManyField('videos.Vision', blank=True, related_name='watch_later_by')
    liked_comments = models.ManyToManyField('videos.Comment', blank=True)
    watch_history = models.ManyToManyField('videos.Vision', blank=True, related_name='watch_history_by')
    interests = models.ManyToManyField('Interest', blank=True)
    stripe_customer_id = models.CharField(max_length=50, blank=True, null=True)
    ppv_visions = models.ManyToManyField('videos.Vision', blank=True, related_name='ppv_purchased_by')
    reminder_creators = models.ManyToManyField('Creator', blank=True, related_name='reminded_by')

    def __str__(self):
        return self.user.username

class Creator(models.Model):
    MONETIZATION_STATUS = [
        ('pending', 'Pending Setup'),
        ('onboarding', 'Connect Onboarding'),
        ('active', 'Active'),
        ('disabled', 'Disabled')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    subscription_price = models.DecimalField(max_digits=6, decimal_places=2, null=True)
    subscriber_count = models.IntegerField(default=0)
    bio = models.TextField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    subscription_price_id = models.CharField(max_length=100, null=True, blank=True) 
    stripe_connect_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_connect_onboarding_completed = models.BooleanField(default=False)
    monetization_status = models.CharField(
        max_length=20,
        choices=MONETIZATION_STATUS,
        default='pending'
    )
    can_receive_payments = models.BooleanField(default=False)
    search_vector = SearchVectorField(null=True)

    class Meta:
        indexes = [GinIndex(fields=['search_vector'])]

    def __str__(self):
        return self.user.username

    def can_accept_payments(self):
        """Check if creator can accept payments"""
        return (
            self.stripe_connect_id and 
            self.stripe_connect_onboarding_completed and 
            self.monetization_status == 'active' and
            self.can_receive_payments
        )
    
    def get_balance(self):
        """Get creator's current balance from Stripe"""
        if not self.stripe_connect_id:
            return {'available': 0, 'pending': 0}
            
        try:
            import stripe
            balance = stripe.Balance.retrieve(
                stripe_account=self.stripe_connect_id
            )
            
            # Convert amounts from cents to dollars
            available = sum(b.amount for b in balance.available) / 100.0
            pending = sum(b.amount for b in balance.pending) / 100.0
            
            return {
                'available': available,
                'pending': pending
            }
        except Exception as e:
            print(f"Error fetching Stripe balance: {str(e)}")
            return {'available': 0, 'pending': 0}
    
    def get_payout_history(self, limit=10):
        """Get creator's payout history from Stripe"""
        if not self.stripe_connect_id:
            return []
            
        try:
            import stripe
            payouts = stripe.Payout.list(
                stripe_account=self.stripe_connect_id,
                limit=limit
            )
            
            return [{
                'id': p.id,
                'amount': p.amount / 100.0,  # Convert cents to dollars
                'status': p.status,
                'created': p.created,
                'arrival_date': p.arrival_date
            } for p in payouts.data]
        except Exception as e:
            print(f"Error fetching payout history: {str(e)}")
            return []

class SignInCodeRequest(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, default=None)
    status = models.CharField(
        max_length=10,
        choices=[('pending', 'Pending'), ('success', 'Success')],
        default='pending'
    )
    code = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SignInCodeRequest {self.id}: {self.status}"

    class Meta:
        ordering = ['-created_at']

class EmailVerificationRequest(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField()
    status = models.CharField(
        max_length=10,
        choices=[('pending', 'Pending'), ('success', 'Success')],
        default='pending'
    )
    code = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Email Verification Request for {self.email}: {self.status}"

    class Meta:
        ordering = ['-created_at']

class BadgeType(models.TextChoices):
    COMMENT = 'CM', 'Comment'
    SUPER_FAN = 'SF', 'Super Fan'
    SUPPORTER = 'SP', 'Supporter'
    EARLY_BIRD = 'EB', 'Early Bird'
    COMMENT_KING = 'CK', 'Comment King'
    TOP_SUPPORTER = 'TS', 'Top Supporter'

class Badge(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    image_url = models.URLField()
    badge_type = models.CharField(max_length=2, choices=BadgeType.choices)
    
    def __str__(self):
        return self.name

class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge')

    def __str__(self):
        return f"{self.user.username} - {self.badge.name}"
    
class CollabInvite(models.Model):
    STATUS_CHOICES = [
        ('ACCEPTED', 'Accepted'),
        ('PENDING', 'Pending'),
        ('DECLINED', 'Declined'),
    ]

    host_creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='sent_collab_invites')
    invited_creators = models.ManyToManyField(Creator, related_name='received_collab_invites')
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, null=True, blank=True)
    vision = models.ForeignKey('videos.Vision', on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notified = models.BooleanField(default=False)  # New field

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(event__isnull=False) | models.Q(vision__isnull=False),
                name='collab_invite_event_or_vision'
            )
        ]

    def __str__(self):
        return f"Collab Invite from {self.host_creator.user.username} - {self.get_status_display()}"

class ActivityItem(models.Model):
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    image_url = models.URLField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.username}'s activity: {self.text[:50]}..."

    class Meta:
        ordering = ['-created_at']

class ActivityEvent(models.Model):
    ACTION_TYPES = [
        ('post', 'Post'),
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('subscribe', 'Subscribe'),
        ('event_create', 'Event Create'),
    ]
    TARGET_TYPES = [
        ('vision', 'Vision'),
        ('event', 'Event'),
        ('comment', 'Comment'),
        ('creator', 'Creator'),
    ]

    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    target_id = models.PositiveIntegerField()
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.actor.username} {self.action_type} {self.target_type}"

class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    event = models.ForeignKey(ActivityEvent, on_delete=models.CASCADE)
    seen = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.event}"

class NotificationTemplate(models.Model):
    key = models.CharField(max_length=50, unique=True)
    template_en = models.TextField()
    template_es = models.TextField()

    def __str__(self):
        return self.key

class WatchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vision = models.ForeignKey('videos.Vision', on_delete=models.CASCADE)
    watched_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    view_duration = models.PositiveIntegerField(default=0)  # Duration in seconds

    class Meta:
        unique_together = ('user', 'vision')
        ordering = ['-watched_at']

class ViewCount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vision = models.ForeignKey('videos.Vision', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    view_duration = models.PositiveIntegerField(default=0)  # Duration in seconds
    is_valid = models.BooleanField(default=True)  # Mark suspicious views as invalid
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['vision', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]
        
    def __str__(self):
        return f"{self.user.username} viewed {self.vision.id} at {self.timestamp}"

class SupportRequest(models.Model):
    ISSUE_TYPES = [
        ('TECHNICAL', 'Technical Issue'),
        ('ACCOUNT', 'Account Issue'),
        ('BILLING', 'Billing Issue'),
        ('FEATURE', 'Feature Request'),
        ('OTHER', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_requests')
    issue_type = models.CharField(max_length=100, choices=ISSUE_TYPES)
    additional_info = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Support Request by {self.user.username} - {self.issue_type}"

    class Meta:
        ordering = ['-created_at']

class Report(models.Model):
    REPORT_TYPES = [
        ('chat', 'Chat'),
        ('comment', 'Comment'),
        ('vision', 'Vision'),
    ]

    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_received')
    type = models.CharField(max_length=10, choices=REPORT_TYPES)
    vision = models.ForeignKey('videos.Vision', on_delete=models.CASCADE, null=True, blank=True)
    chat_message = models.TextField()
    comment = models.ForeignKey('videos.Comment', on_delete=models.CASCADE, null=True, blank=True)
    reason = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report by {self.reporter.username} - {self.type}"

    class Meta:
        ordering = ['-timestamp']
