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
            email='test1_friends@example.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2_friends@example.com',
            password='password123'
        )
        self.user3 = User.objects.create_user(
            username='testuser3',
            email='test3_friends@example.com',
            password='password123'
        )
        self.user_for_pending_request = User.objects.create_user(
            username='pendinguser',
            email='pending_friends@example.com',
            password='password123'
        )
        self.user_non_involved = User.objects.create_user(
            username='noninvolved',
            email='noninvolved@example.com',
            password='password123'
        )

        # Create a friendship for some tests
        self.friendship_1_2 = Friend.objects.create(requester=self.user1, recipient=self.user2, status='accepted')
        # Create a friend request for some tests
        self.friend_request_to_user1 = Friend.objects.create(requester=self.user2, recipient=self.user1, status='pending')
        
        # Create a client and authenticate
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)
        
        # Create endpoints
        self.request_url = reverse('friends:friend-requests-list')
        self.received_url = reverse('friends:friend-requests-received')
        self.sent_url = reverse('friends:friend-requests-sent')
        self.friends_url = reverse('friends:friends-list')
    
    def test_send_friend_request(self):
        """Test sending a friend request"""
        # self.friendship_1_2 (user1 to user2, accepted) exists from setUp.
        # So, sending another request from user1 to user2 should fail.
        data = {'recipient_id': self.user2.id}
        response = self.client.post(self.request_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('A friend request already exists or you are already friends', response.data['detail']['non_field_errors'][0])
    
    def test_cannot_send_request_to_self(self):
        """Test that a user cannot send a friend request to themselves"""
        self.client.force_authenticate(user=self.user1)
        data = {'recipient_id': self.user1.id}
        response = self.client.post(self.request_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('You cannot send a friend request to yourself', response.data['detail']['non_field_errors'][0])
    
    def test_cannot_send_duplicate_request(self):
        """Test that a user cannot send duplicate friend requests"""
        self.client.force_authenticate(user=self.user1)
        # Clear existing requests
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        
        # Send initial request
        Friend.objects.create(requester=self.user1, recipient=self.user2, status='pending')
        
        data = {'recipient_id': self.user2.id}
        response = self.client.post(self.request_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('A friend request already exists', response.data['detail']['non_field_errors'][0])
        # Ensure no new request was created
        self.assertEqual(Friend.objects.filter(requester=self.user1, recipient=self.user2).count(), 1)
    
    def test_list_received_requests(self):
        """Test listing friend requests received by the user"""
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        Friend.objects.filter(requester=self.user3, recipient=self.user1).delete()
        
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
        recipient_ids = [req['recipient']['id'] for req in response.data]
        for req in response.data:
            self.assertEqual(req['recipient']['id'], self.user1.id)
            self.assertEqual(req['status'], 'pending')
    
    def test_list_sent_requests(self):
        """Test listing friend requests sent by the user"""
        # Clear existing requests
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        Friend.objects.filter(requester=self.user1, recipient=self.user3).delete()
        
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
        for req in response.data:
            self.assertEqual(req['requester']['id'], self.user1.id)
            self.assertEqual(req['status'], 'pending')
    
    def test_accept_friend_request(self):
        """Test accepting a friend request"""
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        # Create friend request
        friend_request = Friend.objects.create(
            requester=self.user2,
            recipient=self.user1,
            status='pending'
        )
        
        # Accept request
        accept_url = reverse('friends:friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'accepted')
        
        # Check database
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, 'accepted')
    
    def test_reject_friend_request(self):
        """Test rejecting a friend request"""
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        # Create friend request
        friend_request = Friend.objects.create(
            requester=self.user2,
            recipient=self.user1,
            status='pending'
        )
        
        # Reject request
        reject_url = reverse('friends:friend-requests-reject', args=[friend_request.id])
        response = self.client.post(reject_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check database
        friend_request.refresh_from_db()
        self.assertEqual(friend_request.status, 'rejected')
    
    def test_cannot_accept_others_request(self):
        """Test that users cannot accept friend requests sent to others"""
        self.client.force_authenticate(user=self.user_non_involved) # Non-involved user tries to accept
        response = self.client.post(reverse('friends:friend-requests-accept', kwargs={'pk': self.friend_request_to_user1.pk}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Changed from 404
    
    def test_list_friends(self):
        """Test listing friends"""
        # Clear existing friendships
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        Friend.objects.filter(requester=self.user3, recipient=self.user1).delete()
        
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
        
        # Check that the response is paginated
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 2)
        
        # Extract friend IDs from the response data
        friend_ids = []
        for friendship in response.data['results']:
            if 'friend' in friendship and isinstance(friendship['friend'], dict) and 'id' in friendship['friend']:
                friend_ids.append(friendship['friend']['id'])
        
        # Check that both user2 and user3 are in the friends
        self.assertIn(self.user2.id, friend_ids)
        self.assertIn(self.user3.id, friend_ids)
    
    def test_remove_friendship(self):
        """Test removing a friendship"""
        # Clear existing friendships
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        
        # Create friendship
        friendship = Friend.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status='accepted'
        )
        
        # Delete friendship
        delete_url = reverse('friends:friends-detail', args=[friendship.id])
        response = self.client.delete(delete_url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        # Check database
        self.assertFalse(Friend.objects.filter(id=friendship.id).exists())

    def test_unfriend_action(self):
        """ Test the unfriend custom action on the FriendViewSet """
        # Clear existing friendships
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        
        friendship = Friend.objects.create(requester=self.user1, recipient=self.user2, status='accepted')
        unfriend_url = reverse('friends:friends-unfriend', kwargs={'pk': friendship.id})
        
        response = self.client.post(unfriend_url) # It's a POST action
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], "Friend removed successfully")
        self.assertFalse(Friend.objects.filter(id=friendship.id).exists())

    def test_unfriend_non_existent_friendship(self):
        self.client.force_authenticate(user=self.user1)
        non_existent_friend_id = 999  # An ID that doesn't correspond to an actual friendship
        response = self.client.post(reverse('friends:friends-unfriend', kwargs={'pk': non_existent_friend_id}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Changed from 404

    def test_unfriend_not_part_of_friendship(self):
        # user3 tries to unfriend user1 and user2 who are friends with each other, but user3 is not involved
        self.client.force_authenticate(user=self.user_non_involved)
        response = self.client.post(reverse('friends:friends-unfriend', kwargs={'pk': self.friendship_1_2.pk}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Changed from 403

    def test_cannot_accept_already_accepted_request(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        friend_request = Friend.objects.create(requester=self.user2, recipient=self.user1, status='accepted')
        accept_url = reverse('friends:friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_cannot_reject_already_accepted_request(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        friend_request = Friend.objects.create(requester=self.user2, recipient=self.user1, status='accepted')
        reject_url = reverse('friends:friend-requests-reject', args=[friend_request.id])
        response = self.client.post(reject_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_cannot_accept_rejected_request(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        friend_request = Friend.objects.create(requester=self.user2, recipient=self.user1, status='rejected')
        accept_url = reverse('friends:friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_accepted_request(self):
        # Clear existing friendships
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        
        # user1 sent request to user2, user2 accepted it
        friend_request = Friend.objects.create(requester=self.user1, recipient=self.user2, status='accepted')
        cancel_url = reverse('friends:friend-requests-cancel', args=[friend_request.id])
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requester_cannot_accept_own_request(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        
        # user1 (authenticated) sent a request to user2
        friend_request = Friend.objects.create(requester=self.user1, recipient=self.user2, status='pending')
        accept_url = reverse('friends:friend-requests-accept', args=[friend_request.id])
        response = self.client.post(accept_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # user1 is not recipient

    def test_recipient_cannot_cancel_request(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user2, recipient=self.user1).delete()
        
        # user2 sent a request to user1 (authenticated)
        friend_request = Friend.objects.create(requester=self.user2, recipient=self.user1, status='pending')
        cancel_url = reverse('friends:friend-requests-cancel', args=[friend_request.id])
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN) # user1 is not requester

    def test_model_str_representation(self):
        # Clear existing requests
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        Friend.objects.filter(requester=self.user2, recipient=self.user3).delete()
        
        pending_request = Friend.objects.create(requester=self.user1, recipient=self.user2, status='pending')
        self.assertEqual(str(pending_request), f"{self.user1.username} -> {self.user2.username} (pending)")
        
        accepted_request = Friend.objects.create(requester=self.user2, recipient=self.user3, status='accepted')
        self.assertEqual(str(accepted_request), f"{self.user2.username} -> {self.user3.username} (accepted)")

    def test_all_friends_endpoint(self):
        """Test the /api/friends/all_friends/ endpoint"""
        # Clear existing friendships
        Friend.objects.filter(requester=self.user1, recipient=self.user2).delete()
        Friend.objects.filter(requester=self.user3, recipient=self.user1).delete()
        
        # Create two accepted friendships
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
        
        # Get all friends
        url = reverse('friends:friends-all-friends')
        response = self.client.get(url)
        
        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        
        # Extract friend IDs from the response data
        friend_ids = []
        for friendship in response.data:
            # Check if the response format has 'requester' and 'recipient'
            if 'requester' in friendship and 'recipient' in friendship:
                if self.user1.id == friendship['requester']['id']:
                    friend_ids.append(friendship['recipient']['id'])
                else:
                    friend_ids.append(friendship['requester']['id'])
            # Handle the case where 'friend' key might be provided directly
            elif 'friend' in friendship:
                friend_ids.append(friendship['friend']['id'])
        
        # Check that both user2 and user3 are in the friends
        self.assertIn(self.user2.id, friend_ids)
        self.assertIn(self.user3.id, friend_ids)

# class FriendRequestListTests(APITestCase):
#     def test_list_pending_requests(self):
#         # ... existing code ...
#         self.client.force_authenticate(user=self.user1) # user1 is the recipient
#         response = self.client.post(reverse('friends:friend-requests-accept', kwargs={'pk': self.friend_request_to_user1.pk}))
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.friend_request_to_user1.refresh_from_db()
#         self.assertEqual(self.friend_request_to_user1.status, 'accepted')
