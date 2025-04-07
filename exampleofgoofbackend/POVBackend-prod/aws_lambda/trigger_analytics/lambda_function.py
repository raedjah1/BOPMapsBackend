import os
import json
import requests
from datetime import datetime
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    AWS Lambda function to trigger daily analytics snapshot.
    This function should be scheduled to run at midnight UTC.
    """
    try:
        # Get environment variables
        backend_url = os.environ['BACKEND_URL']
        auth_token = os.environ['ANALYTICS_AUTH_TOKEN']
        
        # Construct the full URL
        url = f"{backend_url}/users/trigger-analytics/"
        
        # Make request to backend
        headers = {
            'X-Analytics-Auth-Token': auth_token,
            'Content-Type': 'application/json'
        }
        
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        
        logger.info(f"Analytics triggered successfully at {datetime.utcnow()}")
        return {
            'statusCode': 200,
            'body': json.dumps('Analytics snapshot triggered successfully')
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making request to backend: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        } 