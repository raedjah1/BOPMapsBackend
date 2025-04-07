# users/tests.py

from rest_framework.test import APITestCase, APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

class UserTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

    def test_update_profile_picture(self):
        url = '/users/update-profile-picture/'
        data = {'profile_picture': 'path_to_image'}
        response = self.client.post(url, data, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertIn('profile_picture', response.data)
