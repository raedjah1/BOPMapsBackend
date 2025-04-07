# Note: THese are all Placeholders at the moment
# badges/badge_checker.py

from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from .models import Badge, UserBadge, BadgeType
from users.models import User
from videos.models import Vision, Comment
from events.models import Event
from payments.models import Transaction

def award_badge(user, badge_type):
    badge = Badge.objects.get(badge_type=badge_type)
    UserBadge.objects.get_or_create(user=user, badge=badge)

def check_comment_badge(user):
    comment_count = Comment.objects.filter(user=user).count()
    if comment_count >= 1:
        award_badge(user, BadgeType.COMMENT)

def check_super_fan_badge(user):
    liked_visions = Vision.objects.filter(liked_by=user.spectator).values('creator').annotate(count=Count('creator')).filter(count__gte=25)
    if liked_visions.exists():
        award_badge(user, BadgeType.SUPER_FAN)

def check_supporter_badge(user):
    creator_comment_counts = Comment.objects.filter(user=user).values('vision__creator').annotate(count=Count('vision__creator')).filter(count__gte=25)
    if creator_comment_counts.exists():
        award_badge(user, BadgeType.SUPPORTER)

def check_early_bird_badge(user):
    early_joins = Event.objects.filter(
        remind_me_list=user.spectator,
        start_time__lte=timezone.now() - timedelta(minutes=15)
    ).count()
    if early_joins >= 50:
        award_badge(user, BadgeType.EARLY_BIRD)

def check_comment_king_badge(user):
    comment_count = Comment.objects.filter(user=user).count()
    if comment_count >= 100:
        award_badge(user, BadgeType.COMMENT_KING)

def check_top_supporter_badge(user):
    creator_tip_counts = Transaction.objects.filter(
        from_user=user,
        transaction_type='tip'
    ).values('to_user').annotate(count=Count('to_user')).filter(count__gte=25)
    if creator_tip_counts.exists():
        award_badge(user, BadgeType.TOP_SUPPORTER)

def check_and_award_badges(user):
    check_comment_badge(user)
    check_super_fan_badge(user)
    check_supporter_badge(user)
    check_early_bird_badge(user)
    check_comment_king_badge(user)
    check_top_supporter_badge(user)

# Helper function to be called after relevant actions
def check_badges_after_action(user, action_type):
    if action_type == 'comment':
        check_comment_badge(user)
        check_comment_king_badge(user)
        check_supporter_badge(user)
    elif action_type == 'like_vision':
        check_super_fan_badge(user)
    elif action_type == 'join_event':
        check_early_bird_badge(user)
    elif action_type == 'tip':
        check_top_supporter_badge(user)
    
    # You can add more specific checks here if needed