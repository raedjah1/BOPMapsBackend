from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase
from rest_framework import status
from users.models import User
from .models import Friend

class FriendshipTests(APITestCase):
    def setUp(self):
        """Set up test data"""
        # Create test users
        self.user1 = User.objects.create_user(
            username='testuser1',
            email='test1@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='password123'
        )
        self.user3 = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='password123'
        )
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)
        
        # Create endpoints
        self.request_url = reverse('friend-requests-list')
        self.received_url = reverse('friend-requests-received')
        self.sent_url = reverse('friend-requests-sent')
        self.friends_url = reverse('friends-list')
    
    def test_send_friend_request(self):
        """Test sending a friend request"""
        data = {'recipient': self.user2.id}
        response = self.client.post(self.request_url, data, format='json')
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['recipient'], self.user2.id)
        self.assertEqual(response.data['status'], 'pending')
        
        # Check database
        self.assertTrue(Friend.objects.filter(
            requester=self.user1,
            recipient=self.user2,
            status='pending'
        ).exists())
    
    def test_cannot_send_request_to_self(self):
        """Test that a user cannot send a friend request to themselves"""
        data = {'recipient': self.user1.id}
        response = self.client.post(self.request_url, data, format='json')
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check database
        self.assertFalse(Friend.objects.filter(
            requester=self.user1,
            recipient=self.user1
        ).exists())
    
    def test_cannot_send_duplicate_request(self):
        """Test that a user cannot send duplicate friend requests"""
        # Create existing friend request
        Friend.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status='pending'
        )
        
        # Try to send again
        data = {'recipient': self.user2.id}
        response = self.client.post(self.request_url, data, format='json')
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        # Check database (should still be only one)
        self.assertEqual(Friend.objects.filter(
            requester=self.user1,
            recipient=self.user2
        ).count(), 1)
    
    def test_list_received_requests(self):
        """Test listing friend requests received by the user"""
        # Create friend requests
        Friend.objects.create(
            requester=self.user2,
            recipient=self.user1,
            status='pending'
        )
        Friend.objects.create(
            requester=self.user3,
            recipient=self.user1,
            status='pending'
        )
        
        # Get received requests
        response = self.client.get(self.received_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_list_sent_requests(self):
        """Test listing friend requests sent by the user"""
        # Create friend requests
        Friend.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status='pending'
        )
        Friend.objects.create(
            requester=self.user1,
            recipient=self.user3,
            status='pending'
        )
        
        # Get sent requests
        response = self.client.get(self.sent_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_accept_friend_request(self):
        """Test accepting a friend request"""
        # Create friend request
        friend_request = Friend.objects.create(
            requester=self.user2,
            recipient=self.user1,
            status='pending'
        )
        
        # Accept request
        accept_url = reverse('friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check database
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, 'accepted')
    
    def test_reject_friend_request(self):
        """Test rejecting a friend request"""
        # Create friend request
        friend_request = Friend.objects.create(
            requester=self.user2,
            recipient=self.user1,
            status='pending'
        )
        
        # Reject request
        reject_url = reverse('friend-requests-reject', args=[friend_request.id])
        response = self.client.post(reject_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check database
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, 'rejected')
    
    def test_cannot_accept_others_request(self):
        """Test that users cannot accept friend requests sent to others"""
        # Create friend request to another user
        friend_request = Friend.objects.create(
            requester=self.user2,
            recipient=self.user3,
            status='pending'
        )
        
        # Try to accept
        accept_url = reverse('friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        
        # Check response (should be forbidden)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Check database (status should still be pending)
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, 'pending')
    
    def test_list_friends(self):
        """Test listing friends"""
        # Create accepted friendships
        Friend.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status='accepted'
        )
        Friend.objects.create(
            requester=self.user3,
            recipient=self.user1,
            status='accepted'
        )
        
        # Get friendships
        response = self.client.get(self.friends_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
    
    def test_remove_friendship(self):
        """Test removing a friendship"""
        # Create friendship
        friendship = Friend.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status='accepted'
        )
        
        # Delete friendship
        delete_url = reverse('friends-detail', args=[friendship.id])
        response = self.client.delete(delete_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Check database
        self.assertFalse(Friend.objects.filter(id=friendship.id).exists())
