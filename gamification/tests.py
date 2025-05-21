from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from users.models import User
from .models import Achievement, UserAchievement, PinSkin
from .views import check_achievement_progress
import json

class AchievementTests(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123'
        )
        
        # Create test skin
        self.skin = PinSkin.objects.create(
            name='Test Skin',
            image='test.png',
            description='Test skin description',
            is_premium=True
        )
        
        # Create test achievements
        self.achievement1 = Achievement.objects.create(
            name='Pin Collector',
            description='Collect 10 pins',
            icon='collector.png',
            criteria={
                'type': 'pin_collection',
                'required_count': 10
            }
        )
        
        self.achievement2 = Achievement.objects.create(
            name='Pin Creator',
            description='Create 5 pins',
            icon='creator.png',
            criteria={
                'type': 'pin_count',
                'required_count': 5
            },
            reward_skin=self.skin
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        # Create endpoints
        self.achievements_url = reverse('achievements-list')
        self.user_achievements_url = reverse('user-achievements-list')
        self.skins_url = reverse('skins-list')
        self.owned_skins_url = reverse('skins-owned')
    
    def test_list_achievements(self):
        """Test listing all achievements"""
        response = self.client.get(self.achievements_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Check achievement details are included
        self.assertEqual(response.data[0]['name'], 'Pin Collector')
        self.assertEqual(response.data[1]['name'], 'Pin Creator')
    
    def test_achievement_progress_tracking(self):
        """Test tracking progress towards achievements"""
        # Update progress for pin collection
        check_achievement_progress(
            self.user, 
            'pin_collection', 
            {'count': 5}
        )
        
        # Check progress was recorded
        user_achievement = UserAchievement.objects.get(
            user=self.user,
            achievement=self.achievement1
        )
        self.assertEqual(user_achievement.progress['current_count'], 5)
        
        # Complete the achievement
        check_achievement_progress(
            self.user, 
            'pin_collection', 
            {'count': 5}
        )
        
        # Check achievement is completed
        user_achievement.refresh_from_db()
        self.assertEqual(user_achievement.progress['current_count'], 10)
        self.assertTrue(user_achievement.progress['completed'])
    
    def test_achievement_with_reward(self):
        """Test completing an achievement with a reward skin"""
        # Complete the achievement
        check_achievement_progress(
            self.user, 
            'pin_count', 
            {'count': 5}
        )
        
        # Check if user now owns the reward skin
        response = self.client.get(self.owned_skins_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Find the premium skin in the response
        has_skin = False
        for skin in response.data:
            if skin['name'] == 'Test Skin' and skin['is_premium']:
                has_skin = True
                break
                
        self.assertTrue(has_skin)
    
    def test_equip_skin(self):
        """Test equipping a skin"""
        # Complete achievement to earn skin
        check_achievement_progress(
            self.user, 
            'pin_count', 
            {'count': 5}
        )
        
        # Try to equip the skin
        equip_url = reverse('skins-equip', args=[self.skin.id])
        response = self.client.post(equip_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_cannot_equip_unowned_skin(self):
        """Test that users cannot equip skins they don't own"""
        # Try to equip a premium skin without earning it
        equip_url = reverse('skins-equip', args=[self.skin.id])
        response = self.client.post(equip_url)
        
        # Check response (should be forbidden)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_list_user_achievements(self):
        """Test listing user's achievements"""
        # Add some progress
        check_achievement_progress(
            self.user, 
            'pin_collection', 
            {'count': 5}
        )
        
        response = self.client.get(self.user_achievements_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)  # Only created progress for one achievement
