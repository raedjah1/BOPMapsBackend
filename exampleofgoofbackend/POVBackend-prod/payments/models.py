from datetime import timezone
from django.db import models
from users.models import Creator, User
from videos.models import Comment
from django.utils.timezone import now
from django.db.models import F

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('subscription', 'Subscription'),
        ('tip', 'Tip'),
        ('payout', 'Payout')
    ]
    
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded')
    ]

    from_user = models.ForeignKey(User, related_name='transactions_made', on_delete=models.CASCADE)
    to_user = models.ForeignKey(User, related_name='transactions_received', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')
    stripe_payment_intent_id = models.CharField(max_length=100, null=True, blank=True)
    stripe_transfer_id = models.CharField(max_length=100, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # For additional transaction data

    def __str__(self):
        return f"{self.transaction_type} - {self.from_user} -> {self.to_user}: ${self.amount}"

    class Meta:
        ordering = ['-transaction_date']

class Tip(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True)
    vision = models.ForeignKey('videos.Vision', on_delete=models.SET_NULL, null=True, blank=True, related_name='tips')

    def __str__(self):
        tip_str = f"Tip of ${self.amount} from {self.user.username} to {self.creator.user.username}"
        if self.vision:
            tip_str += f" for vision: {self.vision.title}"
        return tip_str

# Credit System Models
class CreditTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('purchase', 'Purchase'),
        ('subscription', 'Subscription'),
        ('credit_subscription', 'Credit Subscription'),
        ('tip', 'Tip'),
        ('refund', 'Refund'),
        ('vision_request', 'Vision Request'),
        ('one_time_purchase', 'One-time Purchase'),
        ('tier_change', 'Subscription Tier Change'),
        ('topup', 'Credit Top-up'),
        ('subscription_renewal', 'Subscription Renewal')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_transactions')
    amount = models.IntegerField()  # Can be positive (credit) or negative (debit)
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPES)
    reference_id = models.CharField(max_length=255, null=True, blank=True)  # RevenueCat purchase ID or subscription ID
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # For additional transaction data

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} - {self.user.username}: {self.amount} credits"

class CreditBalance(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    spectator_balance = models.IntegerField(default=0)
    creator_balance = models.IntegerField(default=0)
    topup_balance = models.IntegerField(default=0)  # Track top-up credits separately
    topup_expiry_date = models.DateTimeField(null=True, blank=True)  # When topup credits expire
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Spectator: {self.spectator_balance} credits, Creator: {self.creator_balance} credits, TopUp: {self.topup_balance} credits"

    def add_spectator_credits(self, amount):
        # Use F() expression for atomic update
        CreditBalance.objects.filter(user=self.user).update(
            spectator_balance=F('spectator_balance') + amount
        )
        self.refresh_from_db()

    def deduct_spectator_credits(self, amount):
        # First, check if topup credits have expired
        self.check_topup_expired()
        
        # Then check if there are sufficient credits
        if self.spectator_balance < amount:
            raise ValueError("Insufficient spectator credits")
        
        # Use F() expression for atomic update
        CreditBalance.objects.filter(user=self.user).update(
            spectator_balance=F('spectator_balance') - amount
        )
        
        # Also decrease topup_balance but not below 0
        decrease_amount = min(amount, self.topup_balance)
        if decrease_amount > 0:
            CreditBalance.objects.filter(user=self.user).update(
                topup_balance=F('topup_balance') - decrease_amount
            )
        
        self.refresh_from_db()

    def add_creator_credits(self, amount):
        # Use F() expression for atomic update
        CreditBalance.objects.filter(user=self.user).update(
            creator_balance=F('creator_balance') + amount
        )
        self.refresh_from_db()

    def deduct_creator_credits(self, amount):
        # First check if there are sufficient credits
        if self.creator_balance < amount:
            raise ValueError("Insufficient creator credits")
        
        # Use F() expression for atomic update
        CreditBalance.objects.filter(user=self.user).update(
            creator_balance=F('creator_balance') - amount
        )
        self.refresh_from_db()
        
    def add_topup_credits(self, amount):
        """Add credits from topup to both topup_balance and creator_balance, and set expiry date"""
        from datetime import datetime, timezone, timedelta
        
        # Set expiry date based on subscription status
        try:
            # Try to get an active subscription
            subscription = UserSubscription.objects.filter(
                user=self.user,
                status='active'
            ).latest('start_date')
            
            # If there's an active subscription, expire at next renewal date
            if subscription.next_renewal_date:
                expiry_date = subscription.next_renewal_date
            else:
                # Fallback to 7 days if no renewal date
                expiry_date = datetime.now(timezone.utc) + timedelta(days=7)
                
        except UserSubscription.DoesNotExist:
            # Try to get any non-active subscription
            try:
                subscription = UserSubscription.objects.filter(
                    user=self.user
                ).exclude(status='active').latest('start_date')
                
                # For non-active subscriptions, use end_date if available
                if subscription.end_date:
                    expiry_date = subscription.end_date
                else:
                    # Fallback to 7 days
                    expiry_date = datetime.now(timezone.utc) + timedelta(days=7)
                    
            except UserSubscription.DoesNotExist:
                # No subscription at all, expire after 7 days
                expiry_date = datetime.now(timezone.utc) + timedelta(days=7)
        
        # Update balances and expiry date
        CreditBalance.objects.filter(user=self.user).update(
            topup_balance=F('topup_balance') + amount,
            spectator_balance=F('spectator_balance') + amount,
            topup_expiry_date=expiry_date
        )
        self.refresh_from_db()
        
    def check_topup_expired(self):
        """Check if topup credits have expired and reset if needed"""
        from datetime import datetime, timezone
        
        if self.topup_balance > 0 and self.topup_expiry_date and self.topup_expiry_date < datetime.now(timezone.utc):
            CreditBalance.objects.filter(user=self.user).update(
                spectator_balance=F('spectator_balance') - self.topup_balance,
            )

            # Top-up credits have expired, reset to 0
            CreditBalance.objects.filter(user=self.user).update(
                topup_balance=0
            )

            self.refresh_from_db()

class ProcessedRevenueCatEvent(models.Model):
    """Tracks RevenueCat webhook events that have been processed to avoid duplicate processing."""
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    product_id = models.CharField(max_length=255, null=True, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-processed_at']
        indexes = [
            models.Index(fields=['event_id']),
        ]
    
    def __str__(self):
        return f"{self.event_type} - {self.event_id[:10]}... - {self.processed_at}"

class UserSubscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
        ('expired', 'Expired'),
        ('refunded', 'Refunded')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_subscriptions')
    tier = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                              help_text="Legacy field - no longer used. Use product_id instead.")
    product_id = models.CharField(max_length=255, null=True, blank=True, help_text="RevenueCat product ID in format subscription_monthly_{credits}")
    credits_per_month = models.IntegerField(default=0, help_text="Number of credits received per month")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    revenuecat_id = models.CharField(max_length=255, unique=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField(null=True, blank=True)
    last_renewal_date = models.DateTimeField(null=True, blank=True)
    next_renewal_date = models.DateTimeField(null=True, blank=True)
    is_trial = models.BooleanField(default=False, help_text="Whether this subscription is in a trial period")
    cancel_reason = models.CharField(max_length=255, null=True, blank=True, help_text="Reason for cancellation if provided by RevenueCat")
    # New fields for tracking subscription changes
    has_pending_change = models.BooleanField(default=False, help_text="Whether this subscription has a pending change (e.g. downgrade)")
    pending_product_id = models.CharField(max_length=255, null=True, blank=True, help_text="Product ID that will take effect at renewal")
    pending_change_date = models.DateTimeField(null=True, blank=True, help_text="Date when pending change will take effect")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        # Add constraint to ensure a user can only have one subscription (regardless of status)
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                name='unique_subscription_per_user'
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.product_id or 'Unknown Product'} ({self.status})"
