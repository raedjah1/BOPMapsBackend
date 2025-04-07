from django.db import models
from users.models import Creator
from django.utils import timezone

class BaseSnapshot(models.Model):
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE)
    date = models.DateField(db_index=True)
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['creator', 'date'])
        ]

class SubscriptionSnapshot(BaseSnapshot):
    total_subscribers = models.IntegerField(default=0)
    new_subscribers = models.IntegerField(default=0)
    churned_subscribers = models.IntegerField(default=0)
    subscription_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('creator', 'date')

class ViewSnapshot(BaseSnapshot):
    total_views = models.IntegerField(default=0)
    subscriber_views = models.IntegerField(default=0)
    non_subscriber_views = models.IntegerField(default=0)
    highlight_views = models.IntegerField(default=0)
    non_highlight_views = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0)
    avg_session_duration = models.FloatField(default=0)

    class Meta:
        unique_together = ('creator', 'date')

class TipSnapshot(BaseSnapshot):
    total_tips = models.IntegerField(default=0)
    total_tip_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unique_tippers = models.IntegerField(default=0)

    class Meta:
        unique_together = ('creator', 'date')

class EngagementSnapshot(BaseSnapshot):
    total_likes = models.IntegerField(default=0)
    total_comments = models.IntegerField(default=0)
    unique_engagers = models.IntegerField(default=0)
    avg_likes_per_vision = models.FloatField(default=0)
    avg_comments_per_vision = models.FloatField(default=0)

    class Meta:
        unique_together = ('creator', 'date')

class DemographicSnapshot(BaseSnapshot):
    age_breakdown = models.JSONField(default=dict)
    gender_breakdown = models.JSONField(default=dict)
    country_breakdown = models.JSONField(default=dict)

    def calculate_percentages(self):
        """Convert raw counts to percentages"""
        for field in [self.age_breakdown, self.gender_breakdown, self.country_breakdown]:
            total = sum(field.values())
            if total > 0:
                for key in field:
                    field[key] = round((field[key] / total) * 100, 2)

    def save(self, *args, **kwargs):
        self.calculate_percentages()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ('creator', 'date')

class RevenueSnapshot(BaseSnapshot):
    subscription_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tip_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tip_percentage = models.FloatField(default=0)

    class Meta:
        unique_together = ('creator', 'date')

    def save(self, *args, **kwargs):
        # Calculate total revenue and tip percentage before saving
        self.total_revenue = self.subscription_revenue + self.tip_revenue
        if self.total_revenue > 0:
            self.tip_percentage = (self.tip_revenue / self.total_revenue) * 100
        super().save(*args, **kwargs)