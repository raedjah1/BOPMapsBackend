from django.db import models

# Create your models here.

class PinSkin(models.Model):
    """
    Model representing visual customizations for pins
    """
    name = models.CharField(max_length=50)
    image = models.ImageField(upload_to='pin_skins/')
    description = models.TextField(blank=True, null=True)
    is_premium = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name


class Achievement(models.Model):
    """
    Model representing achievements that users can unlock
    """
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.ImageField(upload_to='achievements/')
    criteria = models.JSONField(help_text="JSON criteria for achievement completion")
    
    # Optional reward
    reward_skin = models.ForeignKey(
        PinSkin, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='achievement_rewards'
    )
    
    def __str__(self):
        return self.name


class UserAchievement(models.Model):
    """
    Model tracking which users have completed which achievements
    """
    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='achievements'
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='completions'
    )
    completed_at = models.DateTimeField(auto_now_add=True)
    progress = models.JSONField(default=dict, help_text="Current progress towards achievement")
    
    class Meta:
        unique_together = ('user', 'achievement')
    
    def __str__(self):
        return f"{self.user.username} - {self.achievement.name}"
