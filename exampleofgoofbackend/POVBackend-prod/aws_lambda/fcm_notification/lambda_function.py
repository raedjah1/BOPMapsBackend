import json
import os
import logging
import firebase_admin
from firebase_admin import credentials, messaging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Firebase Admin SDK
try:
    cred_file = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if not cred_file:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
    
    logger.info(f"Loading credentials from: {cred_file}")
    
    # Load the service account file from the Lambda package
    try:
        with open(cred_file, 'r') as f:
            cred_json = json.load(f)
            cred = credentials.Certificate(cred_json)
            logger.info("Successfully loaded credentials from file")
    except Exception as file_error:
        logger.error(f"Error loading credentials file: {str(file_error)}")
        raise
    
    if not firebase_admin._apps:  # Only initialize if not already initialized
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    else:
        logger.info("Firebase Admin SDK already initialized")

except Exception as e:
    logger.error(f"Error initializing Firebase Admin SDK: {str(e)}")
    raise

def send_batch(notification, batch_tokens):
    """
    Send notifications to a batch of tokens.
    """
    try:
        if not batch_tokens:
            return {'success_count': 0, 'failure_count': 0}

        # Create a MulticastMessage instead of individual messages
        message = messaging.MulticastMessage(
            notification=notification,
            tokens=batch_tokens
        )
        
        batch_response = messaging.send_multicast(message)
        logger.info(f"Batch processed: {batch_response.success_count} successful, {batch_response.failure_count} failed")
        
        return {
            'success_count': batch_response.success_count,
            'failure_count': batch_response.failure_count
        }
    except Exception as e:
        logger.error(f"Error sending batch notification: {str(e)}")
        return {
            'success_count': 0,
            'failure_count': len(batch_tokens),
            'error': str(e)
        }

def lambda_handler(event, context):
    """
    AWS Lambda handler for sending FCM notifications.
    
    Expected payload format:
    {
        "title": "Notification title",
        "body": "Notification body",
        "tokens": ["token1", "token2", ...]
    }
    
    Returns:
        dict: API Gateway response with results
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Just use the event directly - no need for complex parsing
        payload = event
        
        # Validate required fields
        required_fields = ['title', 'body', 'tokens']
        if not all(key in payload for key in required_fields):
            logger.error("Missing required fields in payload")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required fields. Please provide title, body, and tokens (array).'
                })
            }

        if not isinstance(payload['tokens'], list):
            logger.error("tokens field is not an array")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'tokens must be an array of FCM registration tokens'
                })
            }

        # Remove any duplicate tokens
        tokens = list(set(payload['tokens']))
        
        # Create the notification message
        notification = messaging.Notification(
            title=payload['title'],
            body=payload['body']
        )

        # Process in batches of 500 (FCM limit)
        batch_size = 500
        results = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(0, len(tokens), batch_size):
                batch = tokens[i:i + batch_size]
                futures.append(
                    executor.submit(send_batch, notification, batch)
                )
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing batch: {str(e)}")
                    results.append({
                        'success_count': 0,
                        'failure_count': batch_size
                    })

        # Calculate totals
        total_success = sum(r['success_count'] for r in results)
        total_failure = sum(r['failure_count'] for r in results)
        
        logger.info(f"Notification processing complete: {total_success} successful, {total_failure} failed")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Notifications processed',
                'total_success': total_success,
                'total_failure': total_failure,
                'total_processed': len(tokens),
                'batch_results': results
            })
        }

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        } 