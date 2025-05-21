from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import PinSkin, Achievement, UserAchievement
from .serializers import PinSkinSerializer, AchievementSerializer, UserAchievementSerializer
from .utils import check_achievement_progress
from bopmaps.views import BaseModelViewSet, BaseReadOnlyViewSet
import logging

logger = logging.getLogger('bopmaps')


class PinSkinViewSet(BaseReadOnlyViewSet):
    """
    API viewset for PinSkin - Read only for regular users
    """
    queryset = PinSkin.objects.all()
    serializer_class = PinSkinSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['GET'])
    def unlocked(self, request):
        """
        Get only the skins that the current user has unlocked
        """
        # Non-premium skins are available to everyone
        queryset = PinSkin.objects.filter(is_premium=False)
        
        # Add premium skins that user has unlocked via achievements
        premium_skins = PinSkin.objects.filter(
            is_premium=True,
            achievement_rewards__completions__user=request.user
        )
        
        # Combine querysets
        queryset = queryset.union(premium_skins)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['GET'])
    def owned(self, request):
        """
        Alias for 'unlocked' to match test expectations
        """
        return self.unlocked(request)
        
    @action(detail=True, methods=['POST'])
    def equip(self, request, pk=None):
        """
        Equip a skin for the current user
        """
        skin = self.get_object()
        user = request.user
        
        # Check if user has access to this skin
        if skin.is_premium:
            # Premium skin must be unlocked via achievement
            if not Achievement.objects.filter(
                reward_skin=skin,
                completions__user=user
            ).exists():
                return Response(
                    {"error": "You don't have access to this skin"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            # Set this skin as the user's current skin
            user.current_pin_skin = skin
            user.save(update_fields=['current_pin_skin'])
            
            return Response(
                {"success": True, "message": f"Equipped skin: {skin.name}"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error equipping skin: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class AchievementViewSet(BaseReadOnlyViewSet):
    """
    API viewset for Achievement - Read only for users
    """
    queryset = Achievement.objects.all()
    serializer_class = AchievementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['GET'])
    def completed(self, request):
        """
        Get all achievements completed by the current user
        """
        user_achievements = UserAchievement.objects.filter(user=request.user)
        achievements = Achievement.objects.filter(completions__in=user_achievements)
        
        serializer = self.get_serializer(achievements, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['GET'])
    def in_progress(self, request):
        """
        Get achievements that the user has started but not completed
        """
        # Get all achievements that have progress but are not complete
        user_achievements = UserAchievement.objects.filter(
            user=request.user,
            progress__isnull=False
        ).exclude(
            achievement__in=Achievement.objects.filter(completions__user=request.user)
        )
        
        achievements = Achievement.objects.filter(
            id__in=[ua.achievement_id for ua in user_achievements]
        )
        
        serializer = self.get_serializer(achievements, many=True)
        return Response(serializer.data)


class UserAchievementViewSet(BaseModelViewSet):
    """
    API viewset for UserAchievement - Users can update progress
    """
    serializer_class = UserAchievementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Return only current user's achievements
        """
        return UserAchievement.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        """
        Ensure the user is set to the current user
        """
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['POST'])
    def update_progress(self, request, pk=None):
        """
        Update progress for an achievement
        """
        try:
            user_achievement = self.get_object()
            
            progress_data = request.data.get('progress', {})
            if not isinstance(progress_data, dict):
                return Response(
                    {"error": "Progress must be a JSON object"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update progress
            with transaction.atomic():
                # Merge existing progress with new progress
                current_progress = user_achievement.progress or {}
                current_progress.update(progress_data)
                user_achievement.progress = current_progress
                user_achievement.save()
                
                # Check if achievement is now complete
                achievement = user_achievement.achievement
                self._check_completion(user_achievement, achievement)
                
                serializer = self.get_serializer(user_achievement)
                return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error updating achievement progress: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _check_completion(self, user_achievement, achievement):
        """
        Check if an achievement is complete based on progress
        """
        # This is a simplified check - in a real app, this would be more sophisticated
        # based on the specific criteria in the achievement
        
        # Example: Check if all required criteria are met
        criteria = achievement.criteria
        progress = user_achievement.progress
        
        # Simple check - all criteria keys must exist in progress and have >= the criteria value
        is_complete = True
        for key, value in criteria.items():
            if key not in progress or progress[key] < value:
                is_complete = False
                break
        
        # If complete, update the completion status
        if is_complete and not UserAchievement.objects.filter(
            user=user_achievement.user,
            achievement=achievement,
            completed_at__isnull=False
        ).exists():
            user_achievement.completed_at = timezone.now()
            user_achievement.save(update_fields=['completed_at'])
            
            logger.info(f"User {user_achievement.user.username} completed achievement: {achievement.name}")
            
            # Here you could trigger notifications, rewards, etc.
