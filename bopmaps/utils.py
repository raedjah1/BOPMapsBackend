import logging
import traceback
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.utils import IntegrityError
from django.conf import settings

logger = logging.getLogger('bopmaps')

def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that provides consistent error responses
    and logs exceptions for debugging.
    """
    # Call REST framework's default exception handler first to get the standard response
    response = exception_handler(exc, context)
    
    # If response is None, DRF doesn't handle this exception by default
    if response is None:
        if isinstance(exc, Http404):
            response = Response(
                {'error': 'Not found', 'detail': str(exc)},
                status=status.HTTP_404_NOT_FOUND
            )
        elif isinstance(exc, PermissionDenied):
            response = Response(
                {'error': 'Permission denied', 'detail': str(exc)},
                status=status.HTTP_403_FORBIDDEN
            )
        elif isinstance(exc, ValidationError):
            response = Response(
                {'error': 'Validation error', 'detail': exc.message_dict if hasattr(exc, 'message_dict') else str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        elif isinstance(exc, IntegrityError):
            response = Response(
                {'error': 'Database integrity error', 'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # Generic uncaught exception
            error_message = str(exc)
            error_id = None
            
            # Log the error with traceback for server debugging
            logger.error(
                f"Uncaught exception: {exc.__class__.__name__}: {error_message}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            
            # In production, don't expose detailed error information to the client
            if not settings.DEBUG:
                error_message = "An unexpected error occurred. Please try again later."
            
            response = Response(
                {'error': 'Server error', 'detail': error_message},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # For already handled exceptions, let's add consistency to the format
    else:
        data = response.data
        error_type = exc.__class__.__name__
        
        # Get request details
        request = context.get('request')
        view = context.get('view')
        
        # Log exception details
        logger.error(
            f"Exception in {view.__class__.__name__}: {error_type}: {str(exc)}\n"
            f"Request: {request.method} {request.path}"
        )
        
        # Format the response with consistent structure
        if isinstance(data, list):
            response.data = {'error': error_type, 'detail': data}
        elif isinstance(data, dict):
            if 'detail' in data and isinstance(data, dict) and len(data) == 1:
                response.data = {'error': error_type, 'detail': data['detail']}
            elif not any(k in data for k in ['error', 'detail']):
                response.data = {'error': error_type, 'detail': data}
    
    return response


def create_error_response(error_message, status_code=status.HTTP_400_BAD_REQUEST):
    """
    Helper function to create consistent error responses.
    
    Args:
        error_message: Error message or dict of errors
        status_code: HTTP status code
        
    Returns:
        Response object with consistent error format
    """
    if isinstance(error_message, dict):
        return Response({'error': True, 'detail': error_message}, status=status_code)
    else:
        return Response({'error': True, 'message': str(error_message)}, status=status_code) 