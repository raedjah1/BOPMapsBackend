import boto3
import json
import os
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)

# Load AWS credentials from environment variables
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
FCM_LAMBDA_ARN = os.getenv('FCM_LAMBDA_ARN')

def create_cloudwatch_rule(rule_name: str, schedule_expression: str) -> str:
    """
    Create a CloudWatch Events rule with the given name and schedule.
    
    Args:
        rule_name: Name for the CloudWatch rule
        schedule_expression: Schedule expression (e.g., "at(2024-01-20T10:00:00)")
    
    Returns:
        The ARN of the created rule
    """
    client = boto3.client('events', region_name=AWS_REGION)
    
    response = client.put_rule(
        Name=rule_name,
        ScheduleExpression=schedule_expression,
        State='ENABLED'
    )
    
    return response['RuleArn']

def add_lambda_target(rule_name: str, lambda_arn: str, target_id: str, input_data: dict) -> None:
    """
    Add a Lambda function as a target for a CloudWatch Events rule.
    
    Args:
        rule_name: Name of the CloudWatch rule
        lambda_arn: ARN of the Lambda function to trigger
        target_id: Unique identifier for this target
        input_data: Data to pass to the Lambda function
    """
    client = boto3.client('events', region_name=AWS_REGION)
    
    client.put_targets(
        Rule=rule_name,
        Targets=[{
            'Id': target_id,
            'Arn': lambda_arn,
            'Input': json.dumps(input_data)
        }]
    )

def grant_lambda_permission(rule_arn: str, lambda_arn: str, statement_id: str) -> None:
    """
    Grant permission for CloudWatch Events to invoke the Lambda function.
    
    Args:
        rule_arn: ARN of the CloudWatch rule
        lambda_arn: ARN of the Lambda function
        statement_id: Unique identifier for this permission
    """
    lambda_client = boto3.client('lambda', region_name=AWS_REGION)
    
    try:
        lambda_client.add_permission(
            FunctionName=lambda_arn,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn
        )
    except lambda_client.exceptions.ResourceConflictException:
        # Permission already exists
        pass

def schedule_fcm_notification(event_id, fcm_tokens, notification_time, title, body, update_existing=False, existing_rule_arn=None):
    """
    Schedule FCM notifications using CloudWatch Events and Lambda.
    
    Args:
        event_id (int): The ID of the event
        fcm_tokens (list): List of FCM tokens
        notification_time (datetime): When to send the notification
        title (str): The notification title
        body (str): The notification body
        update_existing (bool): Whether to update an existing rule
        existing_rule_arn (str): ARN of existing rule to update
    
    Returns:
        str: The ARN of the created/updated CloudWatch Events rule
    """
    try:
        # Get Lambda ARN from environment
        lambda_arn = FCM_LAMBDA_ARN
        if not lambda_arn:
            logger.error("FCM_LAMBDA_ARN environment variable not set")
            return None
            
        # Extract region from Lambda ARN
        # Lambda ARN format: arn:aws:lambda:region:account-id:function:function-name
        try:
            lambda_region = lambda_arn.split(':')[3]
            logger.info(f"Using region {lambda_region} from Lambda ARN")
        except (IndexError, AttributeError):
            lambda_region = AWS_REGION
            logger.warning(f"Could not extract region from Lambda ARN, using default: {lambda_region}")
        
        # Create clients with the appropriate region
        events_client = boto3.client('events', region_name=lambda_region)
        lambda_client = boto3.client('lambda', region_name=lambda_region)
        
        # Create the rule name
        rule_name = f"event_{event_id}_notification"
        
        # Prepare the Lambda input
        if not fcm_tokens:
            logger.error(f"No FCM tokens provided for event {event_id}")
            return None

        lambda_input = {
            "title": title,
            "body": body,
            "tokens": fcm_tokens
        }

        if update_existing and existing_rule_arn:
            try:
                # Update existing rule's schedule
                events_client.put_rule(
                    Name=rule_name,
                    ScheduleExpression=f"cron({notification_time.minute} {notification_time.hour} {notification_time.day} {notification_time.month} ? {notification_time.year})"
                )
                
                # Update the target with new notification data
                events_client.put_targets(
                    Rule=rule_name,
                    Targets=[
                        {
                            'Id': f"event_{event_id}_notification_target",
                            'Arn': lambda_arn,
                            'Input': json.dumps(lambda_input)
                        }
                    ]
                )
                
                logger.info(f"Updated existing rule {rule_name} for event {event_id}")
                return existing_rule_arn
                
            except ClientError as e:
                logger.error(f"Error updating rule {rule_name}: {str(e)}")
                # If update fails, try creating new rule
                update_existing = False
        
        if not update_existing:
            # Create new rule
            response = events_client.put_rule(
                Name=rule_name,
                ScheduleExpression=f"cron({notification_time.minute} {notification_time.hour} {notification_time.day} {notification_time.month} ? {notification_time.year})",
                State='ENABLED'
            )
            
            rule_arn = response['RuleArn']
            
            # Add Lambda target to the rule
            events_client.put_targets(
                Rule=rule_name,
                Targets=[
                    {
                        'Id': f"event_{event_id}_notification_target",
                        'Arn': lambda_arn,
                        'Input': json.dumps(lambda_input)
                    }
                ]
            )
            
            # Grant permission to CloudWatch Events to invoke Lambda
            try:
                lambda_client.add_permission(
                    FunctionName=lambda_arn,
                    StatementId=f"event_{event_id}_notification_permission",
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=rule_arn
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    raise
                # If permission already exists, ignore the error
                logger.info(f"Lambda permission already exists for event {event_id}")
            
            logger.info(f"Created new rule {rule_name} for event {event_id}")
            return rule_arn
            
    except Exception as e:
        logger.error(f"Error scheduling notification for event {event_id}: {str(e)}")
        return None 