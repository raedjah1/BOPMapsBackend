import boto3
import asyncio
import os
import logging
import subprocess
import requests
from datetime import datetime

logger = logging.getLogger('stream_moderator')

class StreamModerator:
    def __init__(self, stream_key, sample_interval=10):
        """
        Initialize stream moderator
        stream_key: The unique identifier for the stream
        sample_interval: How often to check the stream (in seconds)
        """
        self.stream_key = stream_key
        self.sample_interval = sample_interval
        self.is_running = False
        self.rekognition = boto3.client('rekognition',
            region_name='us-east-1',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
        )

        print("StreamModerator initialized")

    async def capture_frame(self):
        """Capture a frame from the live stream"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = f"/tmp/frame_{self.stream_key}_{timestamp}.jpg"
        
        try:
            # Use FFmpeg to capture a frame from the RTMP stream
            command = [
                'ffmpeg',
                '-i', f'rtmp://localhost:1935/stream/{self.stream_key}',
                '-vframes', '1',  # Capture single frame
                '-y',  # Overwrite output file
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if os.path.exists(output_path):
                return output_path
            return None
            
        except Exception as e:
            logger.error(f"Error capturing frame: {str(e)}")
            return None

    
    async def check_frame_content(self, frame_path):
        """Check a single frame for inappropriate content"""
        try:
            with open(frame_path, 'rb') as image:
                response = self.rekognition.detect_moderation_labels(
                    Image={'Bytes': image.read()},
                    MinConfidence=80
                )
            
            # Clean up the frame file
            os.remove(frame_path)
            
            # Check for explicit content
            for label in response['ModerationLabels']:
                if label['ParentName'] in ['Explicit Nudity', 'Violence', 'Graphic Violence Or Gore']:
                    return {
                        'is_explicit': True,
                        'label': label['Name'],
                        'confidence': label['Confidence']
                    }
            
            return {'is_explicit': False}
            
        except Exception as e:
            logger.error(f"Error checking frame content: {str(e)}")
            return {'error': str(e)}

    async def notify_backend(self, violation_data):
        """Notify backend about content violation"""
        try:
            callback_url = os.environ.get('BACKEND_URL') + "/visions/stream-violation/"
            payload = {
                "api_key": os.environ.get('NGINX_API_KEY'),
                "stream_key": self.stream_key,
                "violation_type": "explicit_content",
                "violation_data": violation_data,
                "timestamp": datetime.now().isoformat()
            }
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(callback_url, json=payload, verify=False)
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to notify backend: {response.text}")
                
        except Exception as e:
            logger.error(f"Error notifying backend: {str(e)}")

    async def moderate_stream(self):
        """Main moderation loop"""
        self.is_running = True
        violation_count = 0
        max_violations = 3  # Maximum number of violations before stream termination

        print("Moderation loop started")

        while self.is_running:
            try:
                # Capture frame from stream
                print("Capturing frame")
                frame_path = await self.capture_frame()
                print("Frame captured")
                print("Frame path: ", frame_path)

                if not frame_path:
                    continue
                
                # Check frame content
                result = await self.check_frame_content(frame_path)
                print("Frame content checked")
                print("Result: ", result)
                
                if result.get('is_explicit', False) and result.get('confidence', None) > 80:
                    violation_count += 1
                    logger.warning(f"Content violation detected in stream {self.stream_key}")
                    await self.notify_backend(result)
                    
                    # If max violations reached, terminate stream
                    if violation_count >= max_violations:
                        await self.terminate_stream()
                        break
                
                # Wait for next interval
                await asyncio.sleep(self.sample_interval)
                
            except Exception as e:
                logger.error(f"Error in moderation loop: {str(e)}")
                await asyncio.sleep(self.sample_interval)

    async def terminate_stream(self):
        """Terminate the stream"""
        try:
            # First drop the active connection using nginx control API
            drop_url = f"http://localhost/control/drop/publisher?app=stream&name={self.stream_key}"
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(drop_url)
            )
            logger.info(f"Attempting to drop active connection for stream: {self.stream_key}")
            
            # Block the stream key for future attempts
            block_url = "http://127.0.0.1:8080/api/block-stream"
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(f"{block_url}?name={self.stream_key}")
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to block stream key: {response.text}")
            else:
                logger.info(f"Successfully blocked stream key: {self.stream_key}")
            
            # Notify backend to terminate stream
            callback_url = os.environ.get('BACKEND_URL') + "/visions/terminate-stream/"
            payload = {
                "api_key": os.environ.get('NGINX_API_KEY'),
                "stream_key": self.stream_key,
                "reason": "excessive_content_violations"
            }
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: requests.post(callback_url, json=payload, verify=False)
            )
            
            self.is_running = False
            
        except Exception as e:
            logger.error(f"Error terminating stream: {str(e)}")

    def stop(self):
        """Stop the moderation process"""
        self.is_running = False
