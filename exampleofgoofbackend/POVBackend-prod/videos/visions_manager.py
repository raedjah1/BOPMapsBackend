from django.db import models
from django.db.models import Exists, OuterRef, Case, When, BooleanField, Q, Subquery, Count, Value, F, Sum

class VisionManager(models.Manager):
    """
    Custom manager for Vision model that provides optimized database queries.
    
    Usage:
        # Get visions with all annotations in a single query
        visions = Vision.objects.with_all_annotations(request.user)
    """
    def with_is_locked(self, user):
        from users.models import Spectator, User  # Import here to avoid circular import

        # Return basic queryset for unauthenticated users
        if not user or not user.is_authenticated:
            return self.annotate(
                is_locked=Case(
                    When(is_highlight=True, then=False),
                    When(access_type='free', then=False),
                    default=True,
                    output_field=BooleanField()
                )
            )

        # Get blocked status
        blocked_by_creator = Exists(
            User.objects.filter(
                id=OuterRef('creator__user__id'),
                blocked_users=user
            )
        )

        # Get blocked status
        user_blocked_creator = Exists(
            User.objects.filter(
                id=user.id,
                blocked_users=OuterRef('creator__user')
            )
        )

        # Get subscription status
        try:
            spectator = Spectator.objects.get(user=user)
            subscribed_creators = spectator.subscriptions.all()
        except Spectator.DoesNotExist:
            subscribed_creators = Spectator.objects.none()

        queryset = self.get_queryset()
        
        # Filter out visions from creators who have blocked this user
        queryset = queryset.filter(~blocked_by_creator)
        queryset = queryset.filter(~user_blocked_creator)
        
        # Annotate with is_locked flag
        return queryset.annotate(
            is_locked=Case(
                When(is_highlight=True, then=False),
                When(access_type='free', then=False),
                default=~Exists(subscribed_creators.filter(user=OuterRef('creator__user'))),
                output_field=BooleanField()
            )
        )
        
    def with_all_annotations(self, user):
        """
        Comprehensive annotation method that efficiently annotates visions with
        all needed data for serialization in a single database query.
        
        This method adds the following annotations to each Vision:
        - is_locked_db: Whether the vision is locked for the user
        - is_liked_db: Whether the user has liked the vision
        - watched_at_db: When the user last watched the vision
        - comment_count_db: Number of comments on the vision
        - tip_count: Number of tips given to the vision
        - total_tips_received: Total amount of tips received for the vision
        
        These annotations are automatically used by the VisionSerializer if present,
        greatly improving performance by avoiding N+1 query problems.
        
        Args:
            user: The User object to check permissions against.
                 Can be None for unauthenticated users.
                 
        Returns:
            QuerySet: Vision queryset with all annotations.
        """
        from users.models import Spectator, User  # Import here to avoid circular import
        from payments.models import Tip

        # Start with base queryset with comment count
        queryset = self.annotate(
            comment_count_db=Count('comment', distinct=True)
        )
        
        # For unauthenticated users
        if not user or not user.is_authenticated:
            return queryset.annotate(
                is_locked_db=Case(
                    When(is_highlight=True, then=Value(False)),
                    When(access_type='free', then=Value(False)),
                    default=Value(True),
                    output_field=BooleanField()
                ),
                is_liked_db=Value(False, output_field=BooleanField()),
                watched_at_db=Value(None),
                tip_count=Value(0, output_field=Count('tips', distinct=True)),
                total_tips_received=Value(0, output_field=Sum('tips__amount', default=Value(0)))
            )
            
        # For authenticated users
        try:
            # Get spectator once
            spectator = Spectator.objects.get(user=user)
            
            # Get PPV purchases for is_locked check
            ppv_visions = spectator.ppv_visions.all()
            
            # Blocked status
            blocked_by_creator = Exists(
                User.objects.filter(
                    id=OuterRef('creator__user__id'),
                    blocked_users=user
                )
            )
            
            # User has blocked creator
            user_blocked_creator = Exists(
                User.objects.filter(
                    id=user.id,
                    blocked_users=OuterRef('creator__user')
                )
            )
            
            # Watch history
            watch_history = Subquery(
                user.watchhistory_set.filter(
                    vision=OuterRef('pk')
                ).values('watched_at')[:1]
            )
            
            # Liked status
            liked_status = Exists(
                spectator.liked_visions.filter(pk=OuterRef('pk'))
            )
            
            # Filter out visions from creators who blocked the user
            queryset = queryset.filter(~blocked_by_creator)
            queryset = queryset.filter(~user_blocked_creator)
            
            # Filter out private videos where the user is not the private_user
            private_videos_filter = Q(private_user__isnull=False) & ~Q(private_user=user)
            queryset = queryset.filter(~private_videos_filter)
            
            # Comprehensive annotations in a single query
            queryset = queryset.annotate(
                is_locked_db=Case(
                    When(is_highlight=True, then=Value(False)),
                    When(access_type='free', then=Value(False)),
                    When(pk__in=ppv_visions.values('pk'), then=Value(False)),
                    When(creator__in=spectator.subscriptions.all(), then=Value(False)),
                    default=Value(True),
                    output_field=BooleanField()
                ),
                is_liked_db=liked_status,
                watched_at_db=watch_history,
                tip_count=Count('tips', distinct=True),
                total_tips_received=Sum('tips__amount', default=Value(0))
            )
            
        except Spectator.DoesNotExist:
            # User authenticated but no spectator
            # Filter out private videos where the user is not the private_user
            private_videos_filter = Q(private_user__isnull=False) & ~Q(private_user=user)
            queryset = queryset.filter(~private_videos_filter)
            
            return queryset.annotate(
                is_locked_db=Case(
                    When(is_highlight=True, then=Value(False)),
                    When(access_type='free', then=Value(False)),
                    default=Value(True),
                    output_field=BooleanField()
                ),
                is_liked_db=Value(False, output_field=BooleanField()),
                watched_at_db=Value(None),
                tip_count=Value(0, output_field=Count('tips', distinct=True)),
                total_tips_received=Value(0, output_field=Sum('tips__amount', default=Value(0)))
            )