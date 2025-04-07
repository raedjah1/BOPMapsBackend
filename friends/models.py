from django.db import models
from django.conf import settings

class Friend(models.Model):
    """
    Model representing a friendship between two users.
    """
    STATUSES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    )
    
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='friend_requests_sent'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='friend_requests_received'
    )
    status = models.CharField(max_length=10, choices=STATUSES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('requester', 'recipient')
        
    def __str__(self):
        return f"{self.requester.username} -> {self.recipient.username} ({self.status})"
