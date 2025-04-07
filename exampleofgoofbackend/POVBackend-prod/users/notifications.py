import logging
from firebase_admin import messaging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

def send_fcm_notification(user, title, body, data=None):
    """
    Send a Firebase Cloud Messaging notification to a user.
    
    Args:
        user: User model instance
        title: Notification title
        body: Notification body
        data: Optional dictionary of data to send with the notification
    
    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    try:
        if not user.fcm_token:
            logger.warning(f"No FCM token found for user {user.id}")
            return False

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=user.fcm_token,
        )

        response = messaging.send(message)
        logger.info(f"Successfully sent FCM notification: {response}")
        return True

    except Exception as e:
        logger.error(f"Error sending FCM notification to user {user.id}: {str(e)}")
        # If the token is invalid, remove it from the user
        if isinstance(e, messaging.UnregisteredError):
            user.fcm_token = None
            user.save()
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending FCM notification to user {user.id}: {str(e)}")
        return False

def send_batch_notifications(notification, batch_tokens):
    """
    Send notifications to a batch of tokens.
    
    Args:
        notification: messaging.Notification instance
        batch_tokens: List of FCM tokens
    
    Returns:
        dict: Results containing success/failure counts and details
    """
    try:
        messages = [
            messaging.Message(
                notification=notification,
                token=token
            ) for token in batch_tokens
        ]
        batch_response = messaging.send_all(messages)
        return {
            'success_count': batch_response.success_count,
            'failure_count': batch_response.failure_count,
            'responses': [{
                'token': token,
                'success': resp.success,
                'message_id': resp.message_id if resp.success else None,
                'error': str(resp.exception) if resp.exception else None
            } for token, resp in zip(batch_tokens, batch_response.responses)]
        }
    except Exception as e:
        logger.error(f"Error in batch send: {str(e)}")
        return {
            'success_count': 0,
            'failure_count': len(batch_tokens),
            'error': str(e)
        }

def send_fcm_notification_to_multiple_users(users, title, body, data=None):
    """
    Send a Firebase Cloud Messaging notification to multiple users using batch processing.
    
    Args:
        users: Queryset or list of User model instances
        title: Notification title
        body: Notification body
        data: Optional dictionary of data to send with the notification
    
    Returns:
        tuple: (number of successful sends, number of failed sends)
    """
    # Create notification object
    notification = messaging.Notification(
        title=title,
        body=body
    )

    # Extract valid tokens
    tokens = []
    token_to_user = {}  # Map tokens to users for cleanup
    for user in users:
        if user.fcm_token:
            tokens.append(user.fcm_token)
            token_to_user[user.fcm_token] = user
        else:
            logger.warning(f"No FCM token found for user {user.id}")

    if not tokens:
        logger.warning("No valid tokens found")
        return 0, len(users)

    # Process in batches of 500 (FCM limit)
    batch_size = 500
    results = []
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            futures.append(
                executor.submit(send_batch_notifications, notification, batch)
            )
        
        # Collect results
        for future in futures:
            results.append(future.result())

    # Process results and cleanup invalid tokens
    total_success = 0
    total_failure = 0

    for result in results:
        total_success += result['success_count']
        total_failure += result['failure_count']
        
        # Cleanup invalid tokens
        if 'responses' in result:
            for response in result['responses']:
                if not response['success'] and response['token'] in token_to_user:
                    user = token_to_user[response['token']]
                    if 'Unregistered' in str(response['error']):
                        logger.info(f"Removing invalid token for user {user.id}")
                        user.fcm_token = None
                        user.save()

    logger.info(f"Batch notification results - Success: {total_success}, Failure: {total_failure}")
    return total_success, total_failure 