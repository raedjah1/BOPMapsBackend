import time
import logging
import json
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

logger = logging.getLogger('bopmaps')

class RequestLogMiddleware(MiddlewareMixin):
    """
    Middleware that logs all requests including timing information.
    """
    def process_request(self, request):
        request.start_time = time.time()
        
    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            
            # Get user info
            user = None
            user_id = None
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user.username
                user_id = request.user.id
                
            # Log request details
            log_data = {
                'method': request.method,
                'path': request.path,
                'user': user,
                'user_id': user_id,
                'status_code': response.status_code,
                'duration': round(duration * 1000, 2),  # Convert to ms
                'content_length': len(response.content) if hasattr(response, 'content') else 0,
            }
            
            # Only include query params in debug mode
            if settings.DEBUG:
                log_data['query_params'] = dict(request.GET.items())
                
            # Log the request
            if response.status_code >= 500:
                logger.error(f"Request: {json.dumps(log_data)}")
            elif response.status_code >= 400:
                logger.warning(f"Request: {json.dumps(log_data)}")
            else:
                logger.info(f"Request: {json.dumps(log_data)}")
                
        return response


class UpdateLastActivityMiddleware(MiddlewareMixin):
    """
    Middleware that updates a user's last_active timestamp.
    """
    def process_response(self, request, response):
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Limit the frequency of updates to avoid excessive database writes
            # Only update if the user doesn't have a last_active timestamp
            # or if it's been more than 15 minutes since the last update
            update_interval = getattr(settings, 'LAST_ACTIVE_UPDATE_INTERVAL', 15 * 60)  # 15 minutes in seconds
            
            user = request.user
            now = timezone.now()
            
            if not user.last_active or (now - user.last_active).total_seconds() > update_interval:
                try:
                    # Using update_fields to minimize the database operation
                    user.last_active = now
                    user.save(update_fields=['last_active'])
                except Exception as e:
                    logger.warning(f"Error updating last_active for user {user.username}: {str(e)}")
                    
        return response 