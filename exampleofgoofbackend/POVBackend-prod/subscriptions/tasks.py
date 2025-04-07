from datetime import timedelta
import logging
import boto3
from botocore.exceptions import ClientError
from django.utils import timezone
from django.db import transaction
from django.template.loader import render_to_string
from django.conf import settings
from celery import shared_task

from subscriptions.models import Subscription
from payments.models import CreditBalance, CreditTransaction, Transaction

logger = logging.getLogger(__name__)

@shared_task
def process_topup_expirations():
    """
    Process expired topup credits for all users.
    - Finds all users with a topup balance > 0
    - Checks if their topup credits have expired
    - Resets topup balance to 0 if expired
    """
    logger.info(f"Processing topup credit expirations at {timezone.now()}")
    
    # Get all credit balances with topup_balance > 0
    balances = CreditBalance.objects.filter(topup_balance__gt=0)
    logger.info(f"Found {balances.count()} users with topup balances")
    
    expired_count = 0
    for balance in balances:
        try:
            # Store the previous topup balance
            prev_balance = balance.topup_balance
            
            # Check if credits have expired
            balance.check_topup_expired()
            
            # If balance changed, credits were expired
            if prev_balance > 0 and balance.topup_balance == 0:
                expired_count += 1
                logger.info(f"Expired {prev_balance} topup credits for user {balance.user.id}")
        except Exception as e:
            logger.error(f"Error processing topup expiration for user {balance.user.id}: {str(e)}")
    
    logger.info(f"Completed topup expiration processing. Expired credits for {expired_count} users")
    return expired_count

@shared_task
def process_due_subscriptions():
    """
    Process subscriptions that are due for renewal.
    - Checks if spectator has sufficient credits
    - If yes, renews the subscription
    - If no, downgrades the subscription to free and sends notification
    """
    now = timezone.now()
    logger.info(f"Processing subscription renewals at {now}")
    
    # Get all subscriptions due for renewal (next_payment_date <= now)
    subscriptions_due = Subscription.objects.filter(
        next_payment_date__lte=now,
        is_active=True,
        subscription_type='paid'
    )
    
    logger.info(f"Found {subscriptions_due.count()} subscriptions due for renewal")
    
    for subscription in subscriptions_due:
        try:
            process_subscription_renewal(subscription)
        except Exception as e:
            logger.error(f"Error processing subscription {subscription.id}: {str(e)}")
    
    # After processing renewals, also handle subscriptions that need to be ended
    process_ending_subscriptions()


@shared_task
def process_ending_subscriptions():
    """
    Process subscriptions that have reached their end date and should be terminated.
    - Finds paid subscriptions with end_date in the past that are still active
    - Deactivates them and sends notifications
    """
    now = timezone.now()
    logger.info(f"Processing subscriptions to end at {now}")
    
    # Find paid subscriptions with an end_date in the past that are still active
    ending_subscriptions = Subscription.objects.filter(
        end_date__lt=now,
        is_active=True,
        subscription_type='paid'
    )
    
    logger.info(f"Found {ending_subscriptions.count()} subscriptions to end")
    
    for subscription in ending_subscriptions:
        try:
            end_subscription(subscription)
        except Exception as e:
            logger.error(f"Error ending subscription {subscription.id}: {str(e)}")


def end_subscription(subscription):
    """
    End a subscription that has reached its end date
    - Marks the subscription as inactive
    - Sends notification to the spectator
    - Updates subscription counts
    """
    spectator = subscription.spectator
    creator = subscription.creator
    
    logger.info(f"Ending subscription {subscription.id} - Spectator: {spectator.user.username}, Creator: {creator.user.username}")
    
    # Process with transaction atomicity
    try:
        with transaction.atomic():
            # Mark subscription as inactive
            subscription.is_active = False
            subscription.save()
            
            # If the spectator is in the creator's subscribers list, update it
            try:
                if creator in spectator.subscriptions.all():
                    spectator.subscriptions.remove(creator)
                    
                    # Update creator's subscriber count
                    if creator.subscriber_count > 0:  # Ensure we don't go negative
                        creator.subscriber_count -= 1
                        creator.save()
            except Exception as e:
                logger.error(f"Error updating subscription counts for subscription {subscription.id}: {str(e)}")
            
            # Send notification email
            send_subscription_ended_email(subscription)
            
            logger.info(f"Successfully ended subscription {subscription.id}")
            
    except Exception as e:
        logger.error(f"Error ending subscription {subscription.id}: {str(e)}")
        raise


def send_subscription_ended_email(subscription):
    """
    Send an email to notify spectator that their subscription has ended
    """
    spectator = subscription.spectator
    creator = subscription.creator
    
    # Create SES client
    ses_client = boto3.client(
        'ses',
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
        region_name=settings.AWS_REGION
    )
    
    # Prepare email content
    subject = f"Your Subscription to {creator.user.username} Has Ended"
    
    context = {
        'spectator_name': spectator.user.username,
        'creator_name': creator.user.username,
        'end_date': subscription.end_date.strftime('%Y-%m-%d'),
    }
    
    html_message = render_to_string('email/subscription_ended.html', context)
    
    plain_message = f"""
    Hello {spectator.user.username},
    
    Your paid subscription to {creator.user.username} has ended as of {subscription.end_date.strftime('%Y-%m-%d')}.
    
    If you enjoyed the content, please consider subscribing again to continue supporting the creator and 
    accessing their premium content.
    
    Thank you for your past support!
    
    POV Reality Team
    """
    
    try:
        response = ses_client.send_email(
            Source=settings.DEFAULT_FROM_EMAIL,
            Destination={
                'ToAddresses': [spectator.user.email]
            },
            Message={
                'Subject': {
                    'Data': subject
                },
                'Body': {
                    'Text': {
                        'Data': plain_message
                    },
                    'Html': {
                        'Data': html_message
                    }
                }
            }
        )
        logger.info(f"Sent subscription ended email to {spectator.user.email}")
    except ClientError as e:
        logger.error(f"Failed to send subscription ended email: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"Failed to send subscription ended email: {str(e)}")


def process_subscription_renewal(subscription):
    """
    Process a single subscription renewal
    """
    spectator = subscription.spectator
    creator = subscription.creator
    price = creator.subscription_price
    
    logger.info(f"Processing renewal for subscription {subscription.id} - Spectator: {spectator.user.username}, Creator: {creator.user.username}, Price: {price}")
    
    # Process renewal with transaction atomicity
    try:
        with transaction.atomic():
            # Get credit balances with a DB lock
            spectator_balance = CreditBalance.objects.select_for_update().get(user=spectator.user)
            
            # Check if spectator has enough credits
            if spectator_balance.spectator_balance >= price:
                # Process the renewal payment
                creator_balance = CreditBalance.objects.select_for_update().get(user=creator.user)
                
                # Create a transaction record
                tx = Transaction.objects.create(
                    from_user=spectator.user,
                    to_user=creator.user,
                    amount=price,
                    transaction_type='subscription_renewal',
                    status='completed',
                    metadata={
                        'subscription_id': str(subscription.id),
                        'renewal_date': str(timezone.now())
                    }
                )
                
                # Deduct credits from spectator
                spectator_balance.deduct_spectator_credits(price)
                spectator_balance.save()
                
                # Add credits to creator
                creator_balance.add_creator_credits(price)
                creator_balance.save()
                
                # Record credit transactions
                CreditTransaction.objects.create(
                    user=spectator.user,
                    amount=-price,  # Negative for deduction
                    transaction_type='subscription_renewal',
                    reference_id=str(tx.id),
                    metadata={
                        'subscription_id': str(subscription.id),
                        'balance_after': spectator_balance.spectator_balance
                    }
                )
                
                CreditTransaction.objects.create(
                    user=creator.user,
                    amount=price,  # Positive for addition
                    transaction_type='subscription_renewal',
                    reference_id=str(tx.id),
                    metadata={
                        'subscription_id': str(subscription.id),
                        'subscriber_id': str(spectator.user.id),
                        'balance_after': creator_balance.creator_balance
                    }
                )
                
                # Update subscription next payment date
                subscription.next_payment_date = timezone.now() + timedelta(days=30)
                subscription.end_date = None

                subscription.save()
                
                logger.info(f"Successfully renewed subscription {subscription.id}")
                
                # Notify the creator and spectator about successful renewal
                send_successful_renewal_email(subscription)
                
            else:
                # Insufficient credits - downgrade to free subscription
                logger.warning(f"Insufficient credits for subscription {subscription.id}. Downgrading to free.")
                
                # Update subscription to free
                subscription.subscription_type = 'free'
                subscription.end_date = None

                subscription.save()
                
                # Send notification about insufficient funds
                send_insufficient_credits_email(subscription, price, spectator_balance.spectator_balance)
                
    except Exception as e:
        logger.error(f"Transaction error for subscription {subscription.id}: {str(e)}")
        raise


def send_insufficient_credits_email(subscription, price, current_balance):
    """
    Send an email to notify spectator about insufficient credits
    and subscription downgrade to free tier using AWS SES
    """
    spectator = subscription.spectator
    creator = subscription.creator
    
    # Create SES client
    ses_client = boto3.client(
        'ses',
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
        region_name=settings.AWS_REGION
    )
    
    # Prepare email content using template
    subject = "Subscription Downgraded - Insufficient Credits"
    
    context = {
        'spectator_name': spectator.user.username,
        'creator_name': creator.user.username,
        'price': price,
        'current_balance': current_balance,
        'needed_amount': price - current_balance,
    }
    
    html_message = render_to_string('email/insufficient_credits.html', context)
    
    plain_message = f"""
    Hello {spectator.user.username},
    
    We were unable to process your subscription renewal to {creator.user.username} due to insufficient credits.
    
    Subscription price: {price} credits
    Your current balance: {current_balance} credits
    
    Your subscription has been downgraded to the free tier. To restore your paid benefits, 
    please add more credits to your account and subscribe again.
    
    Thank you,
    POV Reality Team
    """
    
    try:
        response = ses_client.send_email(
            Source=settings.DEFAULT_FROM_EMAIL,
            Destination={
                'ToAddresses': [spectator.user.email]
            },
            Message={
                'Subject': {
                    'Data': subject
                },
                'Body': {
                    'Text': {
                        'Data': plain_message
                    },
                    'Html': {
                        'Data': html_message
                    }
                }
            }
        )
        logger.info(f"Sent insufficient credits email to {spectator.user.email}")
    except ClientError as e:
        logger.error(f"Failed to send insufficient credits email: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"Failed to send insufficient credits email: {str(e)}")


def send_successful_renewal_email(subscription):
    """
    Send a confirmation email for successful subscription renewal using AWS SES
    """
    spectator = subscription.spectator
    creator = subscription.creator
    
    # Create SES client
    ses_client = boto3.client(
        'ses',
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
        region_name=settings.AWS_REGION
    )
    
    # Prepare email content using template
    subject = f"Subscription to {creator.user.username} Renewed Successfully"
    
    context = {
        'spectator_name': spectator.user.username,
        'creator_name': creator.user.username,
        'next_payment_date': subscription.next_payment_date.strftime('%Y-%m-%d'),
    }
    
    html_message = render_to_string('email/subscription_renewed.html', context)
    
    plain_message = f"""
    Hello {spectator.user.username},
    
    Your subscription to {creator.user.username} has been successfully renewed.
    
    Your next payment will be processed on {subscription.next_payment_date.strftime('%Y-%m-%d')}.
    
    Thank you for your continued support!
    
    POV Reality Team
    """
    
    try:
        response = ses_client.send_email(
            Source=settings.DEFAULT_FROM_EMAIL,
            Destination={
                'ToAddresses': [spectator.user.email]
            },
            Message={
                'Subject': {
                    'Data': subject
                },
                'Body': {
                    'Text': {
                        'Data': plain_message
                    },
                    'Html': {
                        'Data': html_message
                    }
                }
            }
        )
        logger.info(f"Sent renewal confirmation email to {spectator.user.email}")
    except ClientError as e:
        logger.error(f"Failed to send renewal confirmation email: {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"Failed to send renewal confirmation email: {str(e)}") 