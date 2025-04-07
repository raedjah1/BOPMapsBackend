from django.db import models
from users.models import Spectator, Creator, User
from django.utils import timezone
from datetime import timedelta


class Subscription(models.Model):
    SUBSCRIPTION_TYPES = [
        ('free', 'Free'),
        ('paid', 'Paid'),
    ]
    
    spectator = models.ForeignKey(Spectator, on_delete=models.CASCADE)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE)
    subscription_type = models.CharField(max_length=10, choices=SUBSCRIPTION_TYPES, default='free')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)
    promotion = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    transaction = models.OneToOneField('payments.Transaction', on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def has_not_expired(self):
        """
        A subscription has not expired if:
        1. It has no end_date, or
        2. Its end_date is in the future
        """
        return self.end_date is None or self.end_date > timezone.now()

    def __str__(self):
        return f'{self.spectator.user.username} subscribed to {self.creator.user.username}'

    def notify_creator(self):
        """Notify creator of new subscriber"""
        from users.notifications import send_fcm_notification
        
        message = (
            f'{self.spectator.user.username} subscribed to your channel!'
            if self.subscription_type == 'paid' else
            f'{self.spectator.user.username} followed your channel!'
        )
        
        send_fcm_notification(
            self.creator.user,
            'New Subscriber',
            message,
            {
                'type': 'subscription',
                'subscription_type': self.subscription_type,
                'subscriber_id': str(self.spectator.user.id)
            }
        )

    def save(self, *args, **kwargs):
        is_new = self.id is None
        
        # Set next_payment_date for paid subscriptions if not already set
        if self.subscription_type == 'paid' and not self.next_payment_date:
            self.next_payment_date = timezone.now() + timedelta(days=30)
            
        super().save(*args, **kwargs)
        if is_new:
            self.notify_creator()

    def apply_promotion(self, promotion):
        """Apply a promotion to the subscription"""
        if promotion and promotion.is_valid():
            if promotion.promotion_type == 'free_trial':
                self.end_date = timezone.now() + timedelta(days=int(promotion.promotion_amount))
                self.next_payment_date = self.end_date
            promotion.increment_redemption()
            return True
        return False

class Promotion(models.Model):
    PROMOTION_TYPES = [
        ('discount', 'Discount'),
        ('free_trial', 'Free Trial'),
    ]
    
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='promotions')
    promotion_type = models.CharField(max_length=20, choices=PROMOTION_TYPES, default='discount')
    promotion_amount = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage for discount, days for free trial
    end_date = models.DateTimeField(null=True, blank=True)
    redemption_limit = models.IntegerField(null=True, blank=True)
    redemption_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.promotion_type == 'discount':
            return f"Discount promotion by {self.creator.user.username}: {self.promotion_amount}% off"
        elif self.promotion_type == 'free_trial':
            return f"Free trial promotion by {self.creator.user.username}: {self.promotion_amount} days"

    def is_valid(self):
        """Check if the promotion is still valid"""
        if not self.is_active:
            return False
            
        if self.end_date and self.end_date < timezone.now():
            return False
            
        if self.redemption_limit and self.redemption_count >= self.redemption_limit:
            return False
            
        return True

    def apply_to_price(self, original_price):
        """Apply the promotion to the given price"""
        if not self.is_valid():
            return original_price
            
        if self.promotion_type == 'discount':
            discount = float(original_price) * (float(self.promotion_amount) / 100)
            return max(0, float(original_price) - discount)
        elif self.promotion_type == 'free_trial':
            return 0  # Free trial means first payment is free
            
        return original_price

    def increment_redemption(self):
        """Increment the redemption count"""
        self.redemption_count += 1
        if self.redemption_limit and self.redemption_count >= self.redemption_limit:
            self.is_active = False
        self.save()
