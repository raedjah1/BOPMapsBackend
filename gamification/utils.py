from django.utils import timezone
from .models import Achievement, UserAchievement
import logging

logger = logging.getLogger('bopmaps')

def check_achievement_progress(user, achievement_type, data):
    """
    Check and update progress towards achievements of a specific type.
    
    Args:
        user: User object
        achievement_type: Type of achievement (e.g., 'pin_collection', 'pin_creation')
        data: Dictionary with relevant data for checking achievement progress
    
    Returns:
        List of completed achievements (if any)
    """
    # Find all achievements that match this type
    achievements = Achievement.objects.filter(criteria__type=achievement_type)
    completed_achievements = []
    
    for achievement in achievements:
        # Get or create user achievement record
        user_achievement, created = UserAchievement.objects.get_or_create(
            user=user,
            achievement=achievement,
            defaults={'progress': {}}
        )
        
        # Skip if already completed
        if user_achievement.completed_at:
            continue
            
        # Initialize progress if needed
        if not user_achievement.progress or user_achievement.progress == {}:
            user_achievement.progress = {
                'current_count': 0,
                'completed': False
            }
            
        # Update progress based on achievement type
        if achievement_type == 'pin_collection':
            # Collecting pins
            count = data.get('count', 0)
            current = user_achievement.progress.get('current_count', 0)
            required = achievement.criteria.get('required_count', 0)
            
            # Update progress
            user_achievement.progress['current_count'] = current + count
            
            # Check if completed
            if user_achievement.progress['current_count'] >= required:
                user_achievement.progress['completed'] = True
                user_achievement.completed_at = timezone.now()
                completed_achievements.append(achievement)
                
        elif achievement_type == 'pin_count':
            # Creating pins
            count = data.get('count', 0)
            current = user_achievement.progress.get('current_count', 0)
            required = achievement.criteria.get('required_count', 0)
            
            # Update progress
            user_achievement.progress['current_count'] = current + count
            
            # Check if completed
            if user_achievement.progress['current_count'] >= required:
                user_achievement.progress['completed'] = True
                user_achievement.completed_at = timezone.now()
                completed_achievements.append(achievement)
                
        # Add more achievement types as needed
                
        # Save progress
        user_achievement.save()
        
    return completed_achievements 