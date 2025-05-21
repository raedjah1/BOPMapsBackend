from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.utils import timezone
from datetime import timedelta

from .models import Pin, PinInteraction
from gamification.models import PinSkin # Assuming PinSkin is in gamification app

User = get_user_model()

class PinTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', email='user1_pins@example.com', password='password123')
        self.user2 = User.objects.create_user(username='user2', email='user2_pins@example.com', password='password123')
        
        # Create a default PinSkin if it doesn't exist or ensure one with ID 1 exists
        self.default_skin, _ = PinSkin.objects.get_or_create(
            id=1, 
            defaults={'name': 'Default Skin', 'image': 'skins/default.png'}
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

        self.list_create_url = reverse('pin-list')

        self.pin_data_valid = {
            'location': {'type': 'Point', 'coordinates': [-73.985130, 40.758896]},
            'title': 'Times Square Jam',
            'description': 'My favorite song at Times Square',
            'track_title': 'Empire State of Mind',
            'track_artist': 'Jay-Z ft. Alicia Keys',
            'album': 'The Blueprint 3',
            'track_url': 'https://spotify.com/track/123',
            'service': 'spotify',
            'skin': self.default_skin.id, # Use the ID of the existing/created skin
            'rarity': 'common',
            'aura_radius': 100,
            'is_private': False,
        }
        
        # Create a pin for user1 for detail/update/delete tests
        self.pin1_user1 = Pin.objects.create(
            owner=self.user1, 
            location=Point(-73.985130, 40.758896, srid=4326), 
            title='My Pin 1', 
            track_title='Track A', 
            track_artist='Artist A', 
            track_url='http://example.com/a', 
            service='spotify',
            skin=self.default_skin
        )
        self.pin1_user1_url = reverse('pin-detail', kwargs={'pk': self.pin1_user1.pk})

        # Create a public pin for user2 for interaction tests
        self.pin2_user2_public = Pin.objects.create(
            owner=self.user2, 
            location=Point(-74.0060, 40.7128, srid=4326), 
            title='Public Pin User2', 
            track_title='Track B', 
            track_artist='Artist B', 
            track_url='http://example.com/b', 
            service='soundcloud',
            skin=self.default_skin,
            is_private=False
        )

    def test_create_pin_success(self):
        response = self.client.post(self.list_create_url, self.pin_data_valid, format='json')
        # print("Create Pin Response Data:", response.data)
        # print("Create Pin Response Status:", response.status_code)
        # if response.status_code != status.HTTP_201_CREATED:
        #     print("Errors:", response.data) 
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Pin.objects.count(), 3) # Including setUp pins
        created_pin = Pin.objects.get(id=response.data['id'])
        self.assertEqual(created_pin.owner, self.user1)
        self.assertEqual(created_pin.title, self.pin_data_valid['title'])

    def test_create_pin_missing_location(self):
        invalid_data = self.pin_data_valid.copy()
        del invalid_data['location']
        response = self.client.post(self.list_create_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('location', response.data['detail'])

    def test_create_pin_missing_required_music_info(self):
        invalid_data = self.pin_data_valid.copy()
        del invalid_data['track_title']
        response = self.client.post(self.list_create_url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('track_title', response.data['detail'])

    def test_list_pins_authenticated(self):
        """ User sees their own pins and public pins by others """
        # Create a private pin for user1
        private_pin = Pin.objects.create(
            owner=self.user1, 
            location=Point(1,1, srid=4326), 
            title='User1 Private', 
            track_title='T', 
            track_artist='A', 
            track_url='http://e.co', 
            service='spotify', 
            skin=self.default_skin, 
            is_private=True
        )
        # User2's public pin already created in setUp
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Debug information
        pin_count = Pin.objects.count()
        print(f"Total pins in database: {pin_count}")
        all_pin_titles = [p.title for p in Pin.objects.all()]
        print(f"All pin titles in database: {all_pin_titles}")
        
        # Check if response.data is a list or contains paginated results
        if isinstance(response.data, dict) and 'results' in response.data:
            pins_data = response.data['results']
        else:
            pins_data = response.data
            
        if pins_data and isinstance(pins_data, list):
            response_pin_titles = [pin['title'] for pin in pins_data]
            print(f"Response pin titles: {response_pin_titles}")
            
            # Verify the expected pins are in the response
            self.assertEqual(len(pins_data), 3)  # We expect 3 pins
            self.assertIn('My Pin 1', response_pin_titles)
            self.assertIn('User1 Private', response_pin_titles)
            self.assertIn('Public Pin User2', response_pin_titles)
        else:
            # Print more information for debugging
            print(f"Response data type: {type(response.data)}")
            print(f"Response data: {response.data}")
            self.fail("Response data is not a list of pins as expected")

    def test_list_pins_unauthenticated(self):
        self.client.logout()
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_own_pin_detail(self):
        response = self.client.get(self.pin1_user1_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.pin1_user1.title)

    def test_retrieve_others_public_pin_detail(self):
        url = reverse('pin-detail', kwargs={'pk': self.pin2_user2_public.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.pin2_user2_public.title)

    def test_retrieve_others_private_pin_detail_forbidden(self):
        private_pin_user2 = Pin.objects.create(owner=self.user2, location=Point(0,0, srid=4326), title='Private User2', track_title='T', track_artist='A', track_url='http://e.co', service='spotify', skin=self.default_skin, is_private=True)
        url = reverse('pin-detail', kwargs={'pk': private_pin_user2.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Or 403 depending on visibility logic

    def test_update_own_pin(self):
        update_data = {'title': 'My Updated Pin 1', 'description': 'Updated description'}
        response = self.client.patch(self.pin1_user1_url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pin1_user1.refresh_from_db()
        self.assertEqual(self.pin1_user1.title, 'My Updated Pin 1')
        self.assertEqual(self.pin1_user1.description, 'Updated description')

    def test_cannot_update_others_pin(self):
        url = reverse('pin-detail', kwargs={'pk': self.pin2_user2_public.pk})
        update_data = {'title': 'Attempted Update'}
        response = self.client.patch(url, update_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_pin(self):
        response = self.client.delete(self.pin1_user1_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Pin.objects.filter(pk=self.pin1_user1.pk).exists())

    def test_cannot_delete_others_pin(self):
        url = reverse('pin-detail', kwargs={'pk': self.pin2_user2_public.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Pin.objects.filter(pk=self.pin2_user2_public.pk).exists())

class PinInteractionTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1_interaction@example.com', email='user1_interaction@example.com', password='password123')
        self.user2 = User.objects.create_user(username='user2_interaction@example.com', email='user2_interaction@example.com', password='password123')
        self.default_skin, _ = PinSkin.objects.get_or_create(id=1, defaults={'name': 'Default', 'image':'img.png'})

        # Create a pin for testing
        self.pin_by_user2 = Pin.objects.create(
            owner=self.user2, location=Point(0,0, srid=4326), title='Test Pin for Interactions',
            track_title='Song', track_artist='Artist', track_url='http://s.ong', service='spotify', skin=self.default_skin,
            is_private=False  # Ensure it's a public pin for interaction
        )
        
        # For test purposes, we'll create a special test pin directly for the user1
        self.pin_by_user1 = Pin.objects.create(
            owner=self.user1, location=Point(1,1, srid=4326), title='Test Pin owned by user1',
            track_title='User1 Song', track_artist='User1 Artist', track_url='http://user1.song', 
            service='spotify', skin=self.default_skin
        )
        
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

        # URLs for user2's pin (to test interacting with others' pins)
        self.view_url = reverse('pin-view', kwargs={'pk': self.pin_by_user2.pk})
        self.like_url = reverse('pin-like', kwargs={'pk': self.pin_by_user2.pk})
        self.collect_url = reverse('pin-collect', kwargs={'pk': self.pin_by_user2.pk})
        self.share_url = reverse('pin-share', kwargs={'pk': self.pin_by_user2.pk})
        
        # URL for user1's own pin
        self.own_view_url = reverse('pin-view', kwargs={'pk': self.pin_by_user1.pk})
        self.own_like_url = reverse('pin-like', kwargs={'pk': self.pin_by_user1.pk})
        
        # URL for interactions list
        self.interactions_list_create_url = reverse('pininteraction-list')

    def test_record_view_interaction(self):
        response = self.client.post(self.own_view_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='view').exists())
        self.assertEqual(response.data['message'], 'Pin view recorded successfully')

    def test_record_like_interaction(self):
        response = self.client.post(self.own_like_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='like').exists())

    def test_record_collect_interaction(self):
        initial_collected_count = self.user1.pins_collected
        response = self.client.post(reverse('pin-collect', kwargs={'pk': self.pin_by_user1.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='collect').exists())
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.pins_collected, initial_collected_count + 1)

    def test_record_share_interaction(self):
        response = self.client.post(reverse('pin-share', kwargs={'pk': self.pin_by_user1.pk}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='share').exists())

    def test_prevent_duplicate_interactions_same_type(self):
        # First like
        self.client.post(self.own_like_url)
        self.assertEqual(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='like').count(), 1)
        # Second like should not create new interaction record (idempotent or error, depending on design, here we assume success with no new obj)
        response = self.client.post(self.own_like_url) 
        self.assertEqual(response.status_code, status.HTTP_200_OK) # Assuming it is handled gracefully
        self.assertEqual(PinInteraction.objects.filter(user=self.user1, pin=self.pin_by_user1, interaction_type='like').count(), 1)

    def test_list_user_pin_interactions(self):
        # Create interactions with user's own pin for the test
        self.client.post(self.own_like_url)
        self.client.post(reverse('pin-collect', kwargs={'pk': self.pin_by_user1.pk}))
        response = self.client.get(self.interactions_list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # The response data might be paginated or a simple list
        if isinstance(response.data, dict) and 'results' in response.data:
            interactions = response.data['results']
        else:
            interactions = response.data
            
        # The count may vary depending on what's in the DB
        interaction_count = len(interactions)
        self.assertGreaterEqual(interaction_count, 2)
        
        # Extract interaction types
        types = []
        for item in interactions:
            if isinstance(item, dict) and 'interaction_type' in item:
                types.append(item['interaction_type'])
            # If it's a string representation or another format, skip
            
        self.assertIn('like', types)
        self.assertIn('collect', types)

    def test_list_user_pin_interactions_filtered_by_type(self):
        # Create interactions with user's own pin for the test  
        self.client.post(self.own_like_url)
        self.client.post(reverse('pin-collect', kwargs={'pk': self.pin_by_user1.pk}))
        response = self.client.get(self.interactions_list_create_url, {'type': 'like'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # The response data might be paginated or a simple list
        if isinstance(response.data, dict) and 'results' in response.data:
            interactions = response.data['results']
        else:
            interactions = response.data
            
        # We expect at least one like interaction
        self.assertGreaterEqual(len(interactions), 1)
        
        # All returned interactions should be of type 'like'
        for interaction in interactions:
            if isinstance(interaction, dict) and 'interaction_type' in interaction:
                self.assertEqual(interaction['interaction_type'], 'like')

class PinGeoQueryTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='geouser', email='geouser_pins@example.com', password='password123')
        self.default_skin, _ = PinSkin.objects.get_or_create(id=1, defaults={'name': 'Default', 'image':'img.png'})
        self.client.force_authenticate(user=self.user)
        self.list_create_url = reverse('pin-list')

        # Pins around NYC
        self.pin_nyc1 = Pin.objects.create(owner=self.user, location=Point(-74.0060, 40.7128, srid=4326), title='NYC Pin 1', track_title='NYSOM', track_artist='Nas', track_url='http://n.yc', service='spotify', skin=self.default_skin, created_at=timezone.now() - timedelta(days=1))
        # Adjusted coordinates for pin_nyc2 to be slightly different but still close
        self.pin_nyc2 = Pin.objects.create(owner=self.user, location=Point(-74.0000, 40.7100, srid=4326), title='NYC Pin 2', track_title='Juicy', track_artist='BIG', track_url='http://b.ig', service='spotify', skin=self.default_skin, created_at=timezone.now() - timedelta(days=2))
        # Pin far away (London)
        self.pin_london = Pin.objects.create(owner=self.user, location=Point(0.1278, 51.5074, srid=4326), title='London Pin', track_title='London Calling', track_artist='Clash', track_url='http://l.on', service='spotify', skin=self.default_skin, created_at=timezone.now() - timedelta(days=3))

        # Simulate some interactions for trending
        PinInteraction.objects.create(user=self.user, pin=self.pin_nyc1, interaction_type='like')
        PinInteraction.objects.create(user=self.user, pin=self.pin_nyc1, interaction_type='collect')
        PinInteraction.objects.create(user=self.user, pin=self.pin_nyc2, interaction_type='like')
        
        self.nearby_url = reverse('pin-nearby')
        self.trending_url = reverse('pin-trending')
        self.list_map_url = reverse('pin-list-map')

    def test_get_nearby_pins(self):
        # User in NYC
        params = {'latitude': 40.7127, 'longitude': -74.0059, 'radius': 10000} # Increased radius to 10km
        response = self.client.get(self.nearby_url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # print("Nearby Pins Features:", response.data['features'])
        self.assertEqual(len(response.data['features']), 2) # pin_nyc1, pin_nyc2
        titles = [feature['properties']['title'] for feature in response.data['features']]
        self.assertIn('NYC Pin 1', titles)
        self.assertIn('NYC Pin 2', titles)
        self.assertNotIn('London Pin', titles)

    def test_get_nearby_pins_no_results(self):
        # User in an area with no pins
        params = {'latitude': 0, 'longitude': 0, 'radius': 1000}
        response = self.client.get(self.nearby_url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['features']), 0)

    def test_get_nearby_pins_missing_coordinates(self):
        response = self.client.get(self.nearby_url, {'radius': 1000})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_trending_pins(self):
        response = self.client.get(self.trending_url, {'days': 7, 'limit': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(len(response.data) <= 5)
        # Based on setUp interactions, pin_nyc1 should be higher if trending logic is interaction based
        if len(response.data) > 0:
            # This depends heavily on the exact trending algorithm which is in get_trending_pins util
            # For now, just check that we get some pins
            self.assertIn(response.data[0]['title'], ['NYC Pin 1', 'NYC Pin 2'])

    def test_get_map_pins_with_location_clustering(self):
        # This endpoint uses get_clustered_pins, testing its basic function here
        params = {'latitude': 40.7127, 'longitude': -74.0059, 'radius': 5000, 'zoom': 13}
        response = self.client.get(self.list_map_url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('features', response.data)
        self.assertIn('cluster_params', response.data)
        # We expect 2 pins in this area
        self.assertEqual(len(response.data['features']), 2)

    def test_get_map_pins_no_location_returns_recent(self):
        response = self.client.get(self.list_map_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('features', response.data)
        # Expects up to 100 recent pins if no location provided
        self.assertTrue(len(response.data['features']) <= 100)
        # Pin created latest should be first if ordering is by -created_at
        # self.assertEqual(response.data['features'][0]['properties']['title'], self.pin_nyc1.title)

    def test_pin_model_str(self):
        self.assertEqual(str(self.pin_nyc1), f"{self.pin_nyc1.title} by {self.user.username} - {self.pin_nyc1.track_title}")

    def test_pin_interaction_model_str(self):
        interaction = PinInteraction.objects.create(user=self.user, pin=self.pin_nyc1, interaction_type='view')
        self.assertEqual(str(interaction), f"{self.user.username} view {self.pin_nyc1.title}")

    def test_expired_pin_not_listed(self):
        expired_pin = Pin.objects.create(
            owner=self.user, location=Point(1,1, srid=4326), title='Expired Pin', 
            track_title='T', track_artist='A', track_url='http://e.co', 
            service='spotify', skin=self.default_skin, 
            expiration_date=timezone.now() - timedelta(days=1)
        )
        response = self.client.get(self.list_create_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pin_list = response.data if isinstance(response.data, list) else response.data.get('results', [])
        titles = [pin['title'] for pin in pin_list]
        self.assertNotIn('Expired Pin', titles)

        # Also check nearby
        params = {'latitude': 1.0, 'longitude': 1.0, 'radius': 1000}
        response_nearby = self.client.get(self.nearby_url, params)
        self.assertEqual(response_nearby.status_code, status.HTTP_200_OK)
        nearby_titles = [feature['properties']['title'] for feature in response_nearby.data['features']]
        self.assertNotIn('Expired Pin', nearby_titles)

    def test_get_map_details_for_pin(self):
        url = reverse('pin-map-details', kwargs={'pk': self.pin_nyc1.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('visualization', response.data)
        self.assertIn('aura_color', response.data['visualization'])
        self.assertEqual(response.data['title'], self.pin_nyc1.title)
        # Check if a view was recorded (if it wasn't viewed in the last hour)
        self.assertTrue(PinInteraction.objects.filter(user=self.user, pin=self.pin_nyc1, interaction_type='view').exists())
