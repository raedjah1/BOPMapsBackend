from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch

User = get_user_model()

class UserAuthTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('users:register')
        self.login_url = reverse('users:token_obtain_pair')
        self.user_data = {
            'username': 'testuser_auth',
            'email': 'auth@example.com',
            'password': 'ComplexP@ssw0rd!',
            'password_confirm': 'ComplexP@ssw0rd!'
        }
        self.login_data = {
            'username': 'testuser_auth',
            'password': 'ComplexP@ssw0rd!'
        }

    def test_user_registration_success(self):
        """
        Ensure new user can be registered.
        """
        response = self.client.post(self.register_url, self.user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().username, 'testuser_auth')
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['user']['username'], self.user_data['username'])

    def test_user_registration_passwords_do_not_match(self):
        """
        Ensure registration fails if passwords do not match.
        """
        invalid_data = self.user_data.copy()
        invalid_data['email'] = 'auth_pw_mismatch@example.com'
        invalid_data['password_confirm'] = 'wrongpassword'
        response = self.client.post(self.register_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_user_registration_existing_username(self):
        """
        Ensure registration fails if username already exists.
        """
        User.objects.create_user(username='testuser_auth', email='another_auth@example.com', password='ComplexP@ssw0rd!')
        new_user_data_same_username = self.user_data.copy()
        new_user_data_same_username['email'] = 'unique_for_this_test@example.com'
        response = self.client.post(self.register_url, new_user_data_same_username, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_user_registration_existing_email(self):
        """
        Ensure registration fails if email already exists.
        """
        User.objects.create_user(username='anotheruser_auth', email='auth@example.com', password='ComplexP@ssw0rd!')
        new_user_data_same_email = self.user_data.copy()
        new_user_data_same_email['username'] = 'unique_username_for_this_test'
        response = self.client.post(self.register_url, new_user_data_same_email, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_user_login_success(self):
        """
        Ensure registered user can log in.
        """
        self.client.post(self.register_url, self.user_data, format='json')
        response = self.client.post(self.login_url, self.login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], self.login_data['username'])

    def test_user_login_invalid_credentials(self):
        """
        Ensure login fails with invalid credentials.
        """
        self.client.post(self.register_url, self.user_data, format='json')
        invalid_login_data = {'username': 'testuser_auth', 'password': 'wrongpassword'}
        response = self.client.post(self.login_url, invalid_login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)

    def test_user_login_nonexistent_user(self):
        """
        Ensure login fails if user does not exist.
        """
        response = self.client.post(self.login_url, self.login_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)

class UserProfileTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='profileuser', email='profile@example.com', password='ComplexP@ssw0rd!')
        self.client.force_authenticate(user=self.user)
        
        self.login_url = reverse('users:token_obtain_pair')
        self.me_url = reverse('users:user-me')
        self.update_profile_url = reverse('users:user-update-profile')
        self.update_location_url = reverse('users:user-update-location')
        self.update_fcm_token_url = reverse('users:user-update-fcm-token')
        # Assume a detail URL for UserViewSet for other users, if applicable (e.g., 'user-detail')
        # self.other_user_url = reverse('user-detail', kwargs={'pk': self.other_user.pk}) 


    def test_get_current_user_profile_me(self):
        """
        Ensure authenticated user can retrieve their own profile.
        """
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], self.user.username)
        self.assertEqual(response.data['email'], self.user.email)

    def test_update_user_profile_success(self):
        """
        Ensure user can update their profile (bio, username).
        """
        update_data = {
            'username': 'newusername',
            'bio': 'This is my new bio.'
        }
        response = self.client.put(self.update_profile_url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newusername')
        self.assertEqual(self.user.bio, 'This is my new bio.')
        self.assertEqual(response.data['username'], 'newusername')

    def test_update_user_profile_change_password(self):
        """
        Ensure user can change their password.
        """
        password_data = {
            'current_password': 'ComplexP@ssw0rd!',
            'new_password': 'newComplexP@ssw0rd!'
        }
        response = self.client.put(self.update_profile_url, password_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify new password works for login
        self.client.logout()
        login_response = self.client.post(self.login_url, {'username': self.user.username, 'password': 'newComplexP@ssw0rd!'})
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)


    def test_update_user_profile_change_password_incorrect_current(self):
        """
        Ensure changing password fails with incorrect current password.
        """
        password_data = {
            'current_password': 'wrongoldpassword',
            'new_password': 'newComplexP@ssw0rd!'
        }
        response = self.client.put(self.update_profile_url, password_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('current_password', response.data)


    def test_update_user_location(self):
        """
        Ensure user can update their location.
        """
        location_data = {'latitude': 40.7128, 'longitude': -74.0060}
        response = self.client.post(self.update_location_url, location_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.location)
        self.assertEqual(self.user.location.x, -74.0060)
        self.assertEqual(self.user.location.y, 40.7128)
        self.assertIn('location', response.data)

    def test_update_user_location_invalid_coordinates(self):
        """
        Ensure updating location fails with invalid coordinates.
        """
        location_data = {'latitude': 'invalid', 'longitude': -74.0060}
        response = self.client.post(self.update_location_url, location_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data) # Or specific field errors

    def test_update_fcm_token(self):
        """
        Ensure user can update their FCM token.
        """
        fcm_data = {'fcm_token': 'new_fcm_token_123'}
        response = self.client.post(self.update_fcm_token_url, fcm_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.fcm_token, 'new_fcm_token_123')
        self.assertTrue(response.data['success'])

    def test_update_fcm_token_missing_token(self):
        """
        Ensure updating FCM token fails if token is missing.
        """
        response = self.client.post(self.update_fcm_token_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)


    def test_unauthenticated_access_to_me_fails(self):
        """
        Ensure unauthenticated users cannot access /me/ endpoint.
        """
        self.client.logout()
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('users.models.User.save') # Mock save to avoid actual DB write during this specific check if needed
    def test_user_model_methods(self, mock_save):
        """ Test various model methods for User """
        user = User(username='modeltest', email='model@test.com')
        user.save() # This will call the mock

        user.update_last_active()
        self.assertTrue(mock_save.called)
        
        # Reset mock for next call
        mock_save.reset_mock() 
        from django.contrib.gis.geos import Point
        user.update_location(Point(-70, 40))
        self.assertTrue(mock_save.called)
        
        mock_save.reset_mock()
        user.increment_pins_created()
        self.assertEqual(user.pins_created, 1)
        self.assertTrue(mock_save.called)

        mock_save.reset_mock()
        user.increment_pins_collected()
        self.assertEqual(user.pins_collected, 1)
        self.assertTrue(mock_save.called)

        self.assertEqual(str(user), 'modeltest')
        self.assertEqual(user.full_name, 'modeltest')
        user.first_name = "Test"
        user.last_name = "User"
        self.assertEqual(user.full_name, 'Test User')

        self.assertFalse(user.is_connected_to_music_service())
        user.spotify_connected = True
        self.assertTrue(user.is_connected_to_music_service())

        self.assertIsNone(user.age)
        from datetime import date, timedelta
        user.date_of_birth = date.today() - timedelta(days=365*20) # Approx 20 years old
        self.assertEqual(user.age, 19)

    def test_ban_unban_user(self):
        """ Test banning and unbanning a user. """
        self.assertFalse(self.user.is_banned)
        self.assertFalse(self.user.check_ban_status())

        self.user.ban_user(reason="Test ban", days=1)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_banned)
        self.assertTrue(self.user.check_ban_status())
        self.assertIsNotNone(self.user.banned_until)

        self.user.unban_user()
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_banned)
        self.assertFalse(self.user.check_ban_status())
        self.assertIsNone(self.user.banned_until)

    def test_expired_ban(self):
        """ Test that an expired ban is automatically lifted. """
        from django.utils import timezone
        from datetime import timedelta
        self.user.ban_user(reason="Expired ban", days=-1) # Ban ended yesterday
        self.user.refresh_from_db()
        
        self.assertTrue(self.user.is_banned) # Initially still marked as banned
        self.assertFalse(self.user.check_ban_status()) # check_ban_status should lift it
        
        self.user.refresh_from_db() # Refresh again to see the effect of check_ban_status
        self.assertFalse(self.user.is_banned)
        self.assertIsNone(self.user.banned_until)

    def test_permanent_ban(self):
        """ Test permanent ban. """
        self.user.ban_user(reason="Permanent ban")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_banned)
        self.assertTrue(self.user.check_ban_status())
        self.assertIsNone(self.user.banned_until)
        
# It would be good to also test PasswordResetRequestView and PasswordResetConfirmView
# However, these often involve email sending which is typically mocked.
# For now, focusing on core auth and profile.

# Example of how you might test PasswordResetRequestView with mocking:
# class PasswordResetTests(APITestCase):
#     def setUp(self):
#         self.user = User.objects.create_user(username='resetuser', email='reset@example.com', password='password123')
#         self.request_reset_url = reverse('password_reset_request') # Ensure this URL name is correct

#     @patch('users.views.send_mail') # Mock the send_mail function
#     def test_password_reset_request_success(self, mock_send_mail):
#         response = self.client.post(self.request_reset_url, {'email': 'reset@example.com'}, format='json')
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(response.data['message'], 'Password reset email sent')
#         mock_send_mail.assert_called_once() # Check that an email was attempted

#     def test_password_reset_request_nonexistent_email(self):
#         response = self.client.post(self.request_reset_url, {'email': 'nonexistent@example.com'}, format='json')
#         self.assertEqual(response.status_code, status.HTTP_200_OK) # Should not reveal email non-existence
#         self.assertEqual(response.data['message'], 'Password reset email sent if the email exists')
