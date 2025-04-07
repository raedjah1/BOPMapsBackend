from django.db import models
from users.models import Creator, User, Interest
from videos.visions_manager import VisionManager
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.fields.jsonb import JSONField
from django.db.models.expressions import Q
import json

# TODO Nearby Vision, GDAL library
# from django.contrib.gis.db import models as gis_models

class Vision(models.Model):
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('uploading', 'Uploading'),
        ('transcoding', 'Transcoding'), 
        ('draft', 'Draft'),
        ('cancelled', 'Cancelled'),
        ('failed', 'Failed'),
        ('live', 'Live'),
        ('pending_upload', 'Pending Upload'),
        ('live_failed', 'Live Failed'),
        ('pending_live', 'Pending Live'),
        ('vod', 'VOD'),
        ('processing', 'Processing'),
    ]

    ACCESS_TYPE_CHOICES = [
        ('free', 'Free'),
        ('premium', 'Premium'),
    ]

    CAMERA_TYPE_CHOICES = [
        ('phone', 'Phone'),
        ('external', 'External'),
        ('none', 'None')
    ]

    QUALITY_CHOICES = [
        ('1080p', '1080p'),
        ('4k', '4K'),
        ('8k', '8K'),
        ('auto', 'Auto')
    ]

    # Fields for recommendation system
    feature_vector = models.BinaryField(null=True, blank=True)  # Store TF-IDF vector
    popularity_score = models.FloatField(default=0.0)  # Computed popularity score
    engagement_score = models.FloatField(default=0.0)  # Computed engagement score
    last_recommendation_update = models.DateTimeField(null=True, blank=True)
    
    # Denormalized fields for faster lookups
    comment_count = models.PositiveIntegerField(default=0, db_index=True)
    
    title = models.CharField(max_length=500)
    thumbnail = models.URLField(max_length=500, null=True)
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, null=True, related_name='vision')
    views = models.IntegerField(default=0, db_index=True)
    url = models.URLField(default='', max_length=500, null=True)
    likes = models.IntegerField(default=0, db_index=True)
    dislikes = models.IntegerField(default=0, db_index=True)
    interests = models.ManyToManyField(Interest, blank=True)
    description = models.TextField()
    live = models.BooleanField(default=False, db_index=True)
    aspect_ratio = models.CharField(
        max_length=6, 
        choices=[('16:9', '16:9'), ('4:3', '4:3'), ('VR180', 'VR180'), ('VR360', 'VR360')],
        blank=True, null=True, default=''
    )
    stereo_mapping = models.CharField(
        max_length=100, 
        choices=[('normal', 'Normal'), ('sidebyside', 'Side By Side'), ('topbottom', 'Top Bottom')],
        default='normal',
        null=True, blank=True
    )
    camera_type = models.CharField(
        max_length=50,
        choices=CAMERA_TYPE_CHOICES,
        default='none'
    )
    quality = models.CharField(
        max_length=5,
        choices=QUALITY_CHOICES,
        default='auto'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    search_vector = SearchVectorField(null=True, blank=True)
    is_highlight = models.BooleanField(default=False)
    is_saved = models.BooleanField(default=False)
    is_interactive = models.BooleanField(default=False)
    story_graph = models.JSONField(null=True, blank=True)  # Store the entire story structure
    private_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, default=None)
    # location = gis_models.PointField(null=True, blank=True)
    objects = VisionManager()  # Replace the default manager with our optimized one
    with_locks = VisionManager()  # Our custom manager
    rtmp_link = models.URLField(max_length=500, null=True, blank=True)
    stream_key = models.CharField(max_length=500, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True
    )
    access_type = models.CharField(
        max_length=50,
        choices=ACCESS_TYPE_CHOICES,
        default='free',
        help_text='Access type for the vision'
    )
    vision_request = models.OneToOneField('VisionRequest', on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_vision')
    ppv_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Pay per view price')
    duration = models.BigIntegerField(null=True, blank=True, help_text='Duration of the video in milliseconds')

    @property
    def tips_received(self):
        """
        Calculate the total amount of tips received for this vision.
        Returns a decimal representing the total amount.
        """
        from django.db.models import Sum
        from decimal import Decimal
        
        # Calculate the sum of all tips related to this vision
        total = self.tips.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        return total

    class Meta:
        indexes = [
            GinIndex(fields=['search_vector']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['live', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['status', 'engagement_score']),
            models.Index(fields=['status', 'popularity_score']),
            models.Index(
                fields=['created_at', 'likes', 'views'],
                name='vision_ranking_idx',
                condition=Q(status='vod')
            ),
        ]

    def __str__(self):
        return self.title

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    vision = models.ForeignKey(Vision, on_delete=models.CASCADE, related_name='comment')
    text = models.TextField()
    likes = models.ManyToManyField(User, related_name='liked_comments', blank=True)
    parent_comment = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Comment by {self.user.username} on {self.vision.title}'
    
    @property
    def like_count(self):
        return self.likes.count()

    def notify_creator(self):
        """Notify vision creator of new comment"""
        from users.notifications import send_fcm_notification
        
        # Only send notification if creator has vision activity notifications enabled
        if self.vision.creator.user.notify_vision_activity:
            send_fcm_notification(
                self.vision.creator.user,
                'New Comment',
                f'{self.user.username} commented on your video "{self.vision.title}"',
                {
                    'vision_id': str(self.vision.id),
                    'comment_id': str(self.id),
                    'type': 'comment'
                }
            )

    def save(self, *args, **kwargs):
        is_new = self.id is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Update the denormalized comment count on the related vision
            Vision.objects.filter(pk=self.vision.pk).update(comment_count=models.F('comment_count') + 1)
            # For new comments, notify the creator and parent comment author
            self.notify_creator()
            if self.parent_comment and self.parent_comment.user.notify_comment_replies:
                from users.notifications import send_fcm_notification
                send_fcm_notification(
                    self.parent_comment.user,
                    'New Reply',
                    f'{self.user.username} replied to your comment on "{self.vision.title}"',
                    {
                        'vision_id': str(self.vision.id),
                        'comment_id': str(self.id),
                        'parent_comment_id': str(self.parent_comment.id),
                        'type': 'comment_reply'
                    }
                )

class Poll(models.Model):
    question = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def total_votes(self):
        return sum(item.votes for item in self.items.all())

    def __str__(self):
        return self.question

class PollItem(models.Model):
    poll = models.ForeignKey(Poll, related_name='items', on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    votes = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    @property
    def percentage(self):
        total = self.poll.total_votes
        return (self.votes / total) * 100 if total > 0 else 0

    def __str__(self):
        return f"{self.text} ({self.votes} votes)"

class Vote(models.Model):
    poll_item = models.ForeignKey(PollItem, related_name='votes_cast', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('poll_item', 'user')

    def __str__(self):
        return f"{self.user.username} voted for {self.poll_item.text}"

class StoryNode(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ready', 'Ready')
    ]

    vision = models.ForeignKey(Vision, on_delete=models.CASCADE, related_name='story_nodes')
    video_url = models.URLField(max_length=500)
    is_local_video = models.BooleanField(default=True)
    question = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"Story Node for {self.vision.title} - {self.question}"

class StoryOption(models.Model):
    node = models.ForeignKey(StoryNode, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=500)
    video_url = models.URLField(max_length=500)
    is_local_video = models.BooleanField(default=True)
    next_node = models.ForeignKey(StoryNode, on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_options')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Option '{self.text}' for {self.node.question}"
    
class Invite(models.Model):
    INVITE_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invites')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='received_invites')
    vision = models.ForeignKey(Vision, on_delete=models.CASCADE, related_name='invites', null=True, blank=True)
    status = models.CharField(max_length=10, choices=INVITE_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('sender', 'creator', 'status')

    def __str__(self):
        return f"Invite from {self.sender.username} to {self.recipient.user.username} - {self.get_status_display()}"
class VisionRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vision_requests')
    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name='received_vision_requests')
    title = models.CharField(max_length=500)
    description = models.TextField()
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    vision = models.OneToOneField(Vision, on_delete=models.SET_NULL, null=True, blank=True, related_name='request')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['requester', 'status']),
            models.Index(fields=['creator', 'status'])
        ]

    def __str__(self):
        return f"Vision Request from {self.requester.username} to {self.creator.user.username} - {self.get_status_display()}"

    def notify_status_change(self):
        """Notify relevant parties of status changes"""
        from users.notifications import send_fcm_notification
        
        if self.status == 'pending':
            # Notify creator of new request
            send_fcm_notification(
                self.creator.user,
                'New Vision Request',
                f'{self.requester.username} has sent you a vision request',
                {
                    'request_id': str(self.id),
                    'type': 'vision_request_new'
                }
            )
        elif self.status == 'accepted':
            # Notify requester that their request was accepted
            send_fcm_notification(
                self.requester,
                'Vision Request Accepted',
                f'{self.creator.user.username} has accepted your vision request',
                {
                    'request_id': str(self.id),
                    'type': 'vision_request_accepted'
                }
            )
        elif self.status == 'rejected':
            # Notify requester that their request was rejected
            send_fcm_notification(
                self.requester,
                'Vision Request Rejected',
                f'{self.creator.user.username} has rejected your vision request',
                {
                    'request_id': str(self.id),
                    'type': 'vision_request_rejected'
                }
            )
        elif self.status == 'completed':
            # Notify requester that their vision is ready
            send_fcm_notification(
                self.requester,
                'Vision Request Completed',
                f'{self.creator.user.username} has completed your vision request',
                {
                    'request_id': str(self.id),
                    'vision_id': str(self.vision.id) if self.vision else None,
                    'type': 'vision_request_completed'
                }
            )
        elif self.status == 'cancelled':
            # Notify creator that request was cancelled
            send_fcm_notification(
                self.creator.user,
                'Vision Request Cancelled',
                f'{self.requester.username} has cancelled their vision request',
                {
                    'request_id': str(self.id),
                    'type': 'vision_request_cancelled'
                }
            )

    def save(self, *args, **kwargs):
        is_new = not self.pk
        if not is_new:
            old_status = VisionRequest.objects.get(pk=self.pk).status
            if old_status != self.status:
                # Status has changed, send notification after save
                super().save(*args, **kwargs)
                self.notify_status_change()
                return
        super().save(*args, **kwargs)
        if is_new:
            # New request, send notification
            self.notify_status_change()

class VisionSimilarity(models.Model):
    """
    Stores precomputed similarity scores between visions for fast recommendation lookups.
    """
    vision = models.ForeignKey(Vision, on_delete=models.CASCADE, related_name='similarities')
    similar_vision = models.ForeignKey(Vision, on_delete=models.CASCADE)
    similarity_score = models.FloatField()  # Content-based similarity
    engagement_boost = models.FloatField(default=0.0)  # Boost based on user engagement
    final_score = models.FloatField()  # Combined similarity and engagement score
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('vision', 'similar_vision')
        indexes = [
            models.Index(fields=['vision', '-final_score']),
            models.Index(fields=['similar_vision', '-final_score'])
        ]

    def __str__(self):
        return f"Similarity between {self.vision.title} and {self.similar_vision.title}"

class AnnoyIndex(models.Model):
    """
    Stores the Annoy index for approximate nearest neighbor searches.
    This allows the index to persist across server restarts.
    """
    index_binary = models.BinaryField(verbose_name="Binary Annoy index data")
    vision_ids_json = models.TextField(verbose_name="Vision IDs mapping as JSON")
    vector_size = models.IntegerField(verbose_name="Size of the feature vectors")
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=True, db_index=True)
    
    @property
    def vision_ids(self):
        """Get the vision IDs as a Python list"""
        return json.loads(self.vision_ids_json)
    
    @vision_ids.setter
    def vision_ids(self, ids_list):
        """Set the vision IDs from a Python list"""
        self.vision_ids_json = json.dumps(ids_list)
    
    class Meta:
        indexes = [
            models.Index(fields=['-created_at']),
        ]
        
    def __str__(self):
        return f"Annoy Index {self.id} - {self.created_at} - Current: {self.is_current}"
