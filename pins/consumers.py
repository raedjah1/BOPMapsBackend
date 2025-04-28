import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
import logging

logger = logging.getLogger('bopmaps')

class PinConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time pin updates
    """
    async def connect(self):
        """
        Handle connection - authenticate user and join channel
        """
        # Get user from scope and validate authentication
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated connection attempt to PinConsumer")
            await self.close()
            return
            
        # Join pins updates group
        self.group_name = 'pins_updates'
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        # Also join user-specific channel for targeted updates
        self.user_channel = f"pins_user_{self.user.id}"
        await self.channel_layer.group_add(
            self.user_channel,
            self.channel_name
        )
        
        logger.info(f"User {self.user.username} connected to pins WebSocket")
        await self.accept()
        
        # Send initial connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to pin updates channel',
            'timestamp': timezone.now().isoformat()
        }))
        
    async def disconnect(self, close_code):
        """
        Handle disconnection - leave channels
        """
        # Leave pins updates group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        # Leave user-specific channel
        if hasattr(self, 'user_channel'):
            await self.channel_layer.group_discard(
                self.user_channel,
                self.channel_name
            )
        
    async def receive(self, text_data):
        """
        Handle messages from WebSocket
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            # Handle client heartbeat
            if message_type == 'heartbeat':
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_response',
                    'timestamp': timezone.now().isoformat()
                }))
                
            # Handle subscription to specific pin updates
            elif message_type == 'subscribe_pin':
                pin_id = data.get('pin_id')
                if pin_id:
                    pin_channel = f"pin_{pin_id}"
                    await self.channel_layer.group_add(
                        pin_channel,
                        self.channel_name
                    )
                    await self.send(text_data=json.dumps({
                        'type': 'subscription_confirmed',
                        'pin_id': pin_id,
                        'timestamp': timezone.now().isoformat()
                    }))
                
        except Exception as e:
            logger.error(f"Error in PinConsumer.receive: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Error processing message',
                'timestamp': timezone.now().isoformat()
            }))
            
    async def broadcast_update(self, event):
        """
        Handle broadcast updates from channel layer
        """
        # Forward the message to WebSocket
        message = event.get('message', {})
        await self.send(text_data=json.dumps(message))
        
    async def pin_update(self, event):
        """
        Handle pin update events
        """
        message = event.get('message', {})
        await self.send(text_data=json.dumps({
            'type': 'pin_update',
            'data': message,
            'timestamp': timezone.now().isoformat()
        }))
        
    async def trending_update(self, event):
        """
        Handle trending pins update events
        """
        message = event.get('message', {})
        await self.send(text_data=json.dumps({
            'type': 'trending_update',
            'data': message,
            'timestamp': timezone.now().isoformat()
        })) 