import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.gis.geos import Point
from users.models import User
from geo.models import UserLocation
import logging

logger = logging.getLogger('bopmaps')

class LocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """
        Handle connection - authenticate user and join channel
        """
        # Get user from scope and validate authentication
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated connection attempt to LocationConsumer")
            await self.close()
            return
            
        # Join user-specific channel
        self.user_channel = f"location_{self.user.id}"
        await self.channel_layer.group_add(
            self.user_channel,
            self.channel_name
        )
        
        logger.info(f"User {self.user.username} connected to location WebSocket")
        await self.accept()
        
    async def disconnect(self, close_code):
        """
        Handle disconnection - leave channel
        """
        # Leave user channel
        if hasattr(self, 'user_channel'):
            await self.channel_layer.group_discard(
                self.user_channel,
                self.channel_name
            )
        
    async def receive(self, text_data):
        """
        Receive location update from client
        """
        try:
            data = json.loads(text_data)
            
            # Save user location to database
            if 'lat' in data and 'lng' in data:
                success = await self.save_user_location(data['lat'], data['lng'])
                
                # Send confirmation back to user
                await self.send(text_data=json.dumps({
                    'success': success,
                    'message': 'Location updated' if success else 'Failed to update location'
                }))
            else:
                await self.send(text_data=json.dumps({
                    'success': False,
                    'message': 'Missing latitude or longitude'
                }))
        except Exception as e:
            logger.error(f"Error in LocationConsumer.receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'success': False,
                'message': 'Error processing location update'
            }))
            
    @database_sync_to_async
    def save_user_location(self, lat, lng):
        """
        Save user location to database
        """
        try:
            location = Point(float(lng), float(lat))
            
            # Create location record
            UserLocation.objects.create(
                user=self.user,
                location=location
            )
            
            # Update user's current location if the model has that field
            if hasattr(self.user, 'current_location'):
                self.user.current_location = location
                self.user.save(update_fields=['current_location'])
            
            logger.info(f"Updated location for user {self.user.username}")
            return True
        except Exception as e:
            logger.error(f"Error saving user location: {str(e)}")
            return False 