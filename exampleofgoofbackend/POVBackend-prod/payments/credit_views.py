import json
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import (
    CreditTransaction, CreditBalance, 
    UserSubscription, Transaction as PaymentTransaction, Tip, ProcessedRevenueCatEvent
)
from users.models import User, Creator
from .serializers import CreditTransactionSerializer


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_credit_balance(request):
    """Get user's current credit balances"""
    try:
        user = User.objects.get(id=request.user.pk)
        balance, created = CreditBalance.objects.get_or_create(
            user=user,
            defaults={'spectator_balance': 0, 'creator_balance': 0, 'topup_balance': 0}
        )
        
        # Check if topup credits have expired
        balance.check_topup_expired()
        
        # Format expiry date for response if it exists
        topup_expiry_date = None
        if balance.topup_balance > 0 and balance.topup_expiry_date:
            topup_expiry_date = balance.topup_expiry_date.isoformat()
        
        return Response({
            'balance': balance.spectator_balance,
            'creator_balance': balance.creator_balance,
            'topup_balance': balance.topup_balance,
            'topup_expiry_date': topup_expiry_date
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_credit_transactions(request):
    """Get paginated list of user's credit transactions"""
    try:
        paginator = PageNumberPagination()
        paginator.page_size = 20
        
        transactions = CreditTransaction.objects.filter(
            user=request.user
        ).order_by('-created_at')
        
        page = paginator.paginate_queryset(transactions, request)
        serializer = CreditTransactionSerializer(page, many=True)
        
        return paginator.get_paginated_response(serializer.data)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_subscription(request):
    """Get user's current subscription status"""
    try:
        subscription = UserSubscription.objects.filter(
            user=request.user,
            status='active'
        ).order_by('-start_date').first()  # Get the most recent active subscription
        
        if not subscription:
            return Response({
                'has_subscription': False
            })
        
        response_data = {
            'has_subscription': True,
            'product_id': subscription.product_id,
            'credits_per_month': subscription.credits_per_month,
            'status': subscription.status,
            'next_renewal_date': subscription.next_renewal_date
        }
        
        # Add information about pending changes if applicable
        if subscription.has_pending_change and subscription.pending_product_id:
            pending_credits = 0
            if 'subscription_monthly_' in subscription.pending_product_id:
                try:
                    credits_part = subscription.pending_product_id.split('subscription_monthly_')[1]
                    pending_credits = int(credits_part)
                except (IndexError, ValueError):
                    pass
                    
            # Determine if this is an upgrade or downgrade
            change_type = 'none'
            if pending_credits < subscription.credits_per_month:
                change_type = 'downgrade'
            elif pending_credits > subscription.credits_per_month:
                change_type = 'upgrade'
                    
            response_data.update({
                'has_pending_change': True,
                'pending_product_id': subscription.pending_product_id,
                'pending_credits_per_month': pending_credits,
                'pending_change_date': subscription.pending_change_date,
                'change_type': change_type,
                'current_tier_until': subscription.pending_change_date,
                'display_message': f"Your subscription will {change_type} to {pending_credits} credits on {subscription.pending_change_date.strftime('%Y-%m-%d')}"
            })
        
        return Response(response_data)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@csrf_exempt
@require_POST
def webhook_revenuecat(request):
    """Handle RevenueCat webhooks"""
    print("Received RevenueCat webhook")
    print(request.body)
    
    # Check if the auth token matches the secret from settings
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return HttpResponse(status=401)
    
    token = auth_header.split(' ')[1]
    if token != 'IJORGIUNG4T98H54989BU4W9H':
        return HttpResponse(status=401)
    
    try:
        payload = json.loads(request.body)
        
        # Check if payload has the expected structure
        if 'event' not in payload:
            return HttpResponse(status=400, content='Invalid payload structure')
            
        event = payload['event']
        event_type = event.get('type')
        
        # Extract event_id for duplicate detection
        event_id = event.get('id')
        if not event_id:
            print("Warning: Event has no ID for deduplication")
            # Generate a pseudo-unique ID if none provided
            import uuid
            event_id = str(uuid.uuid4())
        
        # Check if this event has already been processed
        if ProcessedRevenueCatEvent.objects.filter(event_id=event_id).exists():
            print(f"Duplicate event detected (ID: {event_id}). Skipping processing.")
            return HttpResponse(status=200, content=f'Event {event_id} already processed')
        
        # Get user and subscription data
        app_user_id = event.get('app_user_id')
        product_id = event.get('product_id')
        transaction_id = event.get('transaction_id', event.get('original_transaction_id'))
        period_type = event.get('period_type')  # NORMAL, TRIAL, INTRO
        
        # Debug logging
        print(f"Event type: {event_type}")
        print(f"Event ID: {event_id}")
        print(f"App user ID: {app_user_id}")
        print(f"Product ID: {product_id}")
        print(f"Period type: {period_type}")
        
        # Special handling for TEST events
        if event_type == 'TEST':
            print(f"Received TEST event: {json.dumps(event)}")
            # Mark event as processed even for test events
            ProcessedRevenueCatEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                product_id='test'
            )
            return HttpResponse(status=200, content='TEST event processed successfully')
            
        # Extract credits from product_id (format: subscription_monthly_{credits} or topup_lifetime_{credits})
        credits_per_month = 0
        is_topup = False
        
        if product_id:
            if 'subscription_monthly_' in product_id:
                try:
                    credits_part = product_id.split('subscription_monthly_')[1]
                    credits_per_month = int(credits_part)
                    print(f"Extracted {credits_per_month} credits from subscription product ID: {product_id}")
                except (IndexError, ValueError) as e:
                    print(f"Failed to extract credits from product ID: {product_id}, error: {str(e)}")
                    return HttpResponse(status=400, content=f'Invalid product ID format: {product_id}')
            elif 'topup_lifetime_' in product_id:
                try:
                    credits_part = product_id.split('topup_lifetime_')[1]
                    credits_per_month = int(credits_part)  # Using same variable for consistency
                    is_topup = True
                    print(f"Extracted {credits_per_month} credits from topup product ID: {product_id}")
                except (IndexError, ValueError) as e:
                    print(f"Failed to extract credits from topup product ID: {product_id}, error: {str(e)}")
                    return HttpResponse(status=400, content=f'Invalid topup product ID format: {product_id}')
            else:
                return HttpResponse(status=400, content=f'Product ID does not follow the expected format: {product_id}')
        elif event_type not in ['CANCELLATION', 'UNCANCELLATION', 'SUBSCRIPTION_PAUSED']:
            # For these event types, we don't strictly need a product ID
            return HttpResponse(status=400, content='Missing product ID')
            
        try:
            # Look for the user by revenuecat_uuid field
            user = User.objects.get(revenuecat_uuid=app_user_id)
        except User.DoesNotExist:
            print(f"User not found with RevenueCat ID: {app_user_id}")
            return HttpResponse(status=404, content=f'User not found with RevenueCat ID: {app_user_id}')
        
        with transaction.atomic():
            # Create a record of this event being processed - at the beginning of the transaction
            # This ensures that if an error occurs during processing, the event won't be marked as processed
            event_record = ProcessedRevenueCatEvent.objects.create(
                event_id=event_id,
                event_type=event_type,
                user=user,
                product_id=product_id
            )
            
            if event_type == 'INITIAL_PURCHASE':
                # Handle new subscription (regular or trial)
                if not product_id or credits_per_month <= 0:
                    return HttpResponse(status=400, content='Valid product ID required for INITIAL_PURCHASE')
                    
                balance, _ = CreditBalance.objects.get_or_create(
                    user=user,
                    defaults={'spectator_balance': 0, 'creator_balance': 0}
                )
                
                # First, try to find ANY existing subscription for this user
                existing_subscription = UserSubscription.objects.filter(
                    user=user
                ).order_by('-created_at').first()
                
                if existing_subscription:
                    print(f"Found existing subscription for user_id={user.id}, updating it instead of creating a new one")
                    # If there's an active subscription, mark it as cancelled
                    if existing_subscription.status == 'active':
                        existing_subscription.status = 'cancelled'
                        existing_subscription.end_date = datetime.now(timezone.utc)
                        existing_subscription.cancel_reason = 'Cancelled due to new subscription purchase'
                        existing_subscription.save()
                    
                    # Now reactivate/update it
                    existing_subscription.status = 'active'
                    existing_subscription.product_id = product_id
                    existing_subscription.credits_per_month = credits_per_month
                    existing_subscription.revenuecat_id = transaction_id
                    existing_subscription.start_date = datetime.now(timezone.utc)
                    existing_subscription.end_date = None
                    existing_subscription.is_trial = period_type == 'TRIAL'
                    existing_subscription.cancel_reason = None
                    existing_subscription.has_pending_change = False
                    existing_subscription.pending_product_id = None
                    existing_subscription.pending_change_date = None
                    existing_subscription.next_renewal_date = datetime.now(timezone.utc) + timedelta(days=30)
                    existing_subscription.save()
                    
                    subscription = existing_subscription
                else:
                    # Create a new subscription only if user has no existing subscriptions
                    subscription = UserSubscription.objects.create(
                    user=user,
                    status='active',
                        revenuecat_id=transaction_id,
                        start_date=datetime.now(timezone.utc),
                        is_trial=period_type == 'TRIAL',
                        product_id=product_id,
                        credits_per_month=credits_per_month,
                        next_renewal_date=datetime.now(timezone.utc) + timedelta(days=30)
                    )
                
                # For trials, we don't add credits immediately
                is_trial = period_type == 'TRIAL'
                if not is_trial:
                    balance.add_spectator_credits(credits_per_month)
                
                if not is_trial:
                    CreditTransaction.objects.create(
                        user=user,
                            amount=credits_per_month,
                        transaction_type='credit_subscription',
                            reference_id=transaction_id,
                            metadata={
                                'product_id': product_id,
                                'event_id': event_id
                            }
                    )

                balance.save()
                print(f"Initial purchase processed: User ID={user.id}, Product={product_id}, Credits={credits_per_month}")
                
            elif event_type == 'RENEWAL':
                # Handle subscription renewal
                if not product_id or credits_per_month <= 0:
                    return HttpResponse(status=400, content='Valid product ID required for RENEWAL')
                
                # Check if this is a trial conversion
                is_trial_conversion = event.get('is_trial_conversion', False)
                
                # Find the user's subscription - don't filter by active status to ensure we find any subscription
                try:
                    # Get any subscription for this user, not just active ones
                    subscription = UserSubscription.objects.filter(
                        user=user
                    ).order_by('-created_at').first()
                    
                    if not subscription:
                        raise UserSubscription.DoesNotExist
                    
                    print(f"Found subscription for renewal: user_id={user.id}, subscription_id={subscription.id}, status={subscription.status}")
                    
                    # Update status to active if it's not already
                    if subscription.status != 'active':
                        print(f"Changing subscription status from {subscription.status} to active for renewal")
                        subscription.status = 'active'
                    
                    old_product = subscription.product_id
                    old_credits = subscription.credits_per_month
                    
                    # Check if this renewal includes a scheduled change (from downgrade/upgrade)
                    processed_pending_change = False
                    change_type = None
                    
                    if subscription.has_pending_change and subscription.pending_product_id:
                        pending_product = subscription.pending_product_id
                        
                        # Check if the renewal product matches the pending change
                        if pending_product == product_id:
                            print(f"Processing pending change from {old_product} to {product_id} at renewal")
                            change_type = 'upgrade' if credits_per_month > old_credits else 'downgrade'
                            processed_pending_change = True
                        else:
                            print(f"Warning: Pending product {pending_product} doesn't match renewal product {product_id}")
                    
                    # Update product and credits if they've changed
                    if subscription.product_id != product_id or subscription.credits_per_month != credits_per_month:
                        print(f"Product changed during renewal: {subscription.product_id} -> {product_id}")
                        subscription.product_id = product_id
                        subscription.credits_per_month = credits_per_month
                        
                    # Clear pending change flags
                    subscription.has_pending_change = False
                    subscription.pending_product_id = None
                    subscription.pending_change_date = None
                    
                    # Make sure revenuecat_id is updated if it changed
                    if transaction_id and subscription.revenuecat_id != transaction_id:
                        subscription.revenuecat_id = transaction_id
                        
                    # Update next renewal date
                    subscription.next_renewal_date = datetime.now(timezone.utc) + timedelta(days=30)
                    subscription.last_renewal_date = datetime.now(timezone.utc)
                    
                    # Ensure end_date is None for active subscriptions
                    subscription.end_date = None
                    
                    # Save all changes
                    subscription.save()
                    
                except UserSubscription.DoesNotExist:
                    print(f"No subscription found for user_id={user.id}, creating one for renewal")
                    # Create a new subscription instead of returning an error
                    subscription = UserSubscription.objects.create(
                        user=user,
                        status='active',
                        revenuecat_id=transaction_id,
                        start_date=datetime.now(timezone.utc),
                        product_id=product_id,
                        credits_per_month=credits_per_month,
                        next_renewal_date=datetime.now(timezone.utc) + timedelta(days=30),
                        last_renewal_date=datetime.now(timezone.utc)
                    )
                    
                    # Set initial values
                    old_product = None
                    old_credits = 0
                    processed_pending_change = False
                
                # Get user's credit balance
                balance, _ = CreditBalance.objects.get_or_create(
                    user=user,
                    defaults={'spectator_balance': 0, 'creator_balance': 0}
                )
                
                # If this was a trial, update the subscription
                if subscription.is_trial:
                    subscription.is_trial = False
                
                # Store old balance for reference and logging
                old_balance = balance.spectator_balance
                
                # For renewals, reset the credits to the new subscription amount
                balance.spectator_balance = credits_per_month
                balance.save()
                
                # Record the transaction with appropriate metadata
                renewal_metadata = {
                    'product_id': product_id,
                    'event_id': event_id,
                    'is_trial_conversion': is_trial_conversion,
                    'previous_balance': old_balance
                }
                
                # Add metadata about subscription changes if applicable
                if processed_pending_change:
                    renewal_metadata.update({
                        'processed_pending_change': True,
                        'old_product': old_product,
                        'change_type': change_type
                    })
                
                CreditTransaction.objects.create(
                    user=user,
                    amount=credits_per_month,
                    transaction_type='credit_subscription',
                    reference_id=transaction_id,
                    metadata=renewal_metadata
                )
                
                print(f"Renewal: User_id={user.id}, Reset credits from {old_balance} to {credits_per_month}")
                
            elif event_type == 'CANCELLATION':
                # Handle subscription cancellation - also handles trial cancellations
                try:
                    subscription = UserSubscription.objects.filter(
                    user=user,
                    status='active'
                    ).latest('start_date')  # Get the most recent active subscription
                    
                    subscription.status = 'cancelled'
                    subscription.end_date = datetime.now(timezone.utc)
                    
                    # Get the cancellation reason if provided
                    cancel_reason = event.get('cancel_reason')
                    if cancel_reason:
                        subscription.cancel_reason = cancel_reason
                    
                    # Clear any pending change fields when cancelling
                    subscription.has_pending_change = False
                    subscription.pending_product_id = None
                    subscription.pending_change_date = None
                        
                    subscription.save()
                    
                    # Add log entry
                    print(f"Subscription cancelled: user_id={user.id}, subscription_id={subscription.id}, reason={cancel_reason}")
                    
                except UserSubscription.DoesNotExist:
                    print(f"No active subscription found to cancel for user_id={user.id}")
                    # For cancellation, it's normal if there's no subscription
                    # Just log it and return success
                    return HttpResponse(status=200, content='No active subscription found to cancel')
                
            elif event_type == 'UNCANCELLATION':
                # Handle uncancellation (user resubscribed before end of subscription period)
                try:
                    # Find subscription for this user - we want to update it rather than create a new one
                    subscription = UserSubscription.objects.filter(
                        user=user
                    ).order_by('-created_at').first()

                    subscription.status = 'active'
                    subscription.end_date = None
                    subscription.cancel_reason = None
                    subscription.save()
                    
                    print(f"Subscription uncancelled: user_id={user.id}")
                    
                except Exception as e:
                    print(f"Error processing uncancellation: {str(e)}")
                    return HttpResponse(status=500, content=f'Error processing uncancellation: {str(e)}')
                
            elif event_type == 'REFUND':
                # Handle refund
                if not product_id or credits_per_month <= 0:
                    return HttpResponse(status=400, content='Valid product ID required for REFUND')
                    
                balance = CreditBalance.objects.get(user=user)
                
                # Only deduct credits if they're still available
                if balance.spectator_balance >= credits_per_month:
                    balance.deduct_spectator_credits(credits_per_month)
                    
                    CreditTransaction.objects.create(
                        user=user,
                    amount=-credits_per_month,
                        transaction_type='refund',
                    reference_id=transaction_id,
                    metadata={
                        'product_id': product_id,
                        'event_id': event_id
                    }
                )
                
                # Mark any active subscription as refunded
                try:
                    subscription = UserSubscription.objects.filter(
                        user=user,
                        status='active'
                    ).latest('start_date')  # Get the most recent active subscription
                    
                    subscription.status = 'refunded'
                    subscription.end_date = datetime.now(timezone.utc)
                    subscription.save()
                except UserSubscription.DoesNotExist:
                    pass  # No active subscription to update
                
            elif event_type == 'NON_RENEWING_PURCHASE':
                # Handle one-time purchase (could be a topup or one-time subscription)
                if not product_id or credits_per_month <= 0:
                    return HttpResponse(status=400, content='Valid product ID required for NON_RENEWING_PURCHASE')
                    
                balance, _ = CreditBalance.objects.get_or_create(
                    user=user,
                    defaults={'spectator_balance': 0, 'creator_balance': 0, 'topup_balance': 0}
                )
                
                # Add credits (either to spectator balance or as a topup)
                if is_topup:
                    # For topups, add to both topup_balance and creator_balance
                    balance.add_topup_credits(credits_per_month)
                else:
                    # For regular one-time purchases, add to spectator_balance only
                    balance.add_spectator_credits(credits_per_month)
                
                balance.save()
                
                # Determine the transaction type based on product type
                transaction_type = 'topup' if is_topup else 'one_time_purchase'
                
                # Record transaction
                CreditTransaction.objects.create(
                    user=user,
                    amount=credits_per_month,
                    transaction_type=transaction_type,
                    reference_id=transaction_id,
                    metadata={
                        'product_id': product_id,
                        'event_id': event_id,
                        'is_topup': is_topup
                    }
                )
                
            elif event_type == 'PRODUCT_CHANGE':
                # Handle when a user changes their subscription tier
                new_product_id = event.get('new_product_id')
                if not new_product_id or 'subscription_monthly_' not in new_product_id:
                    return HttpResponse(status=400, content='Valid new_product_id required for PRODUCT_CHANGE')
                
                # Extract credits from new product_id
                try:
                    credits_part = new_product_id.split('subscription_monthly_')[1]
                    new_credits = int(credits_part)
                    print(f"New product credits: {new_credits}")
                except (IndexError, ValueError) as e:
                    return HttpResponse(status=400, content=f'Invalid new product ID format: {new_product_id}')
                
                # Get expiration timestamp (when change will take effect)
                expiration_at_ms = event.get('expiration_at_ms')
                is_immediate_change = True
                expiration_date = None
                
                if expiration_at_ms:
                    expiration_date = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc)
                    # If expiration is more than 1 day in future, it's likely a deferred change
                    is_immediate_change = (expiration_date - datetime.now(timezone.utc)).days <= 1
                
                # Find ANY subscription for this user (not just active ones)
                subscription = UserSubscription.objects.filter(
                    user=user
                ).order_by('-created_at').first()
                
                if subscription:
                    print(f"Found subscription for PRODUCT_CHANGE: user_id={user.id}, subscription_id={subscription.id}, status={subscription.status}")
                    
                    # If it's not active, reactivate it
                    if subscription.status != 'active':
                        print(f"Changing subscription status from {subscription.status} to active for product change")
                        subscription.status = 'active'
                        subscription.end_date = None
                        subscription.cancel_reason = None
                        
                    old_product_id = subscription.product_id
                    old_credits = subscription.credits_per_month
                    
                    # Check whether this subscription was recently reactivated
                    was_recently_reactivated = False
                    if subscription.last_renewal_date is None and subscription.created_at:
                        # If no renewal yet and created recently (e.g., last 10 minutes)
                        time_since_creation = datetime.now(timezone.utc) - subscription.created_at
                        was_recently_reactivated = time_since_creation.total_seconds() < 600  # 10 minutes
                        print(f"Subscription {subscription.id} was recently created/reactivated: {was_recently_reactivated}")
                    
                    # Log the product change
                    print(f"Product change: user_id={user.id}, old_product={old_product_id}, new_product={new_product_id}, immediate={is_immediate_change}")
                    
                    # Determine if this is an upgrade or downgrade
                    is_upgrade = new_credits > old_credits
                    is_downgrade = new_credits < old_credits
                    
                    # Get the user's current credit balance
                    balance = CreditBalance.objects.get(user=user)
                    current_balance = balance.spectator_balance
                    
                    # For downgrades, always treat them as deferred to next renewal
                    # This is especially important when following an UNCANCELLATION event
                    if is_downgrade:
                        is_immediate_change = False
                        
                        # Mark the subscription as having a pending change
                        subscription.has_pending_change = True
                        subscription.pending_product_id = new_product_id
                        subscription.pending_change_date = expiration_date or subscription.next_renewal_date
                        subscription.save()
                        
                        # Add detailed logging for debugging
                        print(f"PRODUCT_CHANGE with DOWNGRADE - Debug info:")
                        print(f"  - Original product: {old_product_id} ({old_credits} credits)")
                        print(f"  - Pending product: {new_product_id} ({new_credits} credits)")
                        print(f"  - Current subscription state: has_pending_change={subscription.has_pending_change}, pending_product_id={subscription.pending_product_id}")
                        print(f"  - Pending change date: {subscription.pending_change_date}")
                        print(f"  - Credit balance: {current_balance} credits")
                        print(f"  - Was recently reactivated: {was_recently_reactivated}")
                        
                        # Ensure credits stay at the old tier level until renewal
                        if current_balance != old_credits:
                            balance.spectator_balance = old_credits
                            balance.save()
                            print(f"Adjusted balance from {current_balance} to {old_credits} for downgrade deferral")
                        
                        # Record the transaction for the change but with amount=0
                        CreditTransaction.objects.create(
                            user=user,
                            amount=0,  # No immediate credit change
                            transaction_type='pending_tier_change',
                            reference_id=transaction_id,
                            metadata={
                                'old_product': old_product_id,
                                'new_product': new_product_id,
                                'old_credits': old_credits,
                                'new_credits': new_credits,
                                'change_type': 'downgrade',
                                'kept_balance': old_credits,
                                'event_id': event_id,
                                'following_uncancellation': was_recently_reactivated,
                                'deferred_until_renewal': True,
                                'renewal_date': subscription.next_renewal_date.isoformat() if subscription.next_renewal_date else None
                            }
                        )
                        
                        print(f"Downgrade deferred: User_id={user.id} scheduled change from {old_product_id} to {new_product_id} at renewal")
                    elif is_immediate_change and is_upgrade:
                        # For upgrades, update subscription immediately
                        subscription.product_id = new_product_id
                        subscription.credits_per_month = new_credits
                        
                        # Reset any pending changes
                        subscription.has_pending_change = False
                        subscription.pending_product_id = None
                        subscription.pending_change_date = None
                        
                        subscription.save()
                        
                        # Set balance to the new amount (don't just add the difference)
                        balance.spectator_balance = new_credits
                        balance.save()
                        
                        # Record the transaction for the credit change
                        CreditTransaction.objects.create(
                            user=user,
                            amount=new_credits - current_balance,  # Show net change
                            transaction_type='tier_change',
                            reference_id=transaction_id,
                            metadata={
                                'old_product': old_product_id,
                                'new_product': new_product_id,
                                'old_credits': old_credits,
                                'new_credits': new_credits,
                                'old_balance': current_balance,
                                'change_type': 'upgrade',
                                'event_id': event_id,
                                'immediate': True
                            }
                        )
                        
                        print(f"Immediate upgrade: Set credits to {new_credits} for user_id={user.id}")
                    else:
                        # For deferred changes (or same tier changes)
                        # Don't update the subscription immediately, just mark it as pending change
                        
                        subscription.has_pending_change = True
                        subscription.pending_product_id = new_product_id
                        subscription.pending_change_date = expiration_date or subscription.next_renewal_date
                        subscription.save()
                        
                        # Record the transaction as a pending change
                        CreditTransaction.objects.create(
                            user=user,
                            amount=0,  # No immediate credit change
                            transaction_type='pending_tier_change',
                            reference_id=transaction_id,
                            metadata={
                                'old_product': old_product_id,
                                'new_product': new_product_id,
                                'old_credits': old_credits,
                                'new_credits': new_credits,
                                'change_type': 'same_tier' if new_credits == old_credits else ('upgrade' if is_upgrade else 'downgrade'),
                                'current_balance': current_balance,
                                'event_id': event_id,
                                'effective_date': (expiration_date or subscription.next_renewal_date).isoformat() if (expiration_date or subscription.next_renewal_date) else None,
                                'immediate': False
                            }
                        )
                        
                        print(f"Deferred change: User_id={user.id} scheduled change from {old_product_id} to {new_product_id} effective at next renewal")
                else:
                    print(f"No subscription found for user_id={user.id}, checking for existing subscription with same revenuecat_id")
                    # Before creating a new subscription, check if there's already one with this revenuecat_id
                    existing_subscription = UserSubscription.objects.filter(
                        user=user,
                        revenuecat_id=transaction_id
                    ).first()
                    
                    if existing_subscription:
                        print(f"Found existing subscription with revenuecat_id={transaction_id}, updating instead of creating")
                        # Update existing subscription instead of creating a new one
                        existing_subscription.status = 'active'
                        existing_subscription.product_id = new_product_id
                        existing_subscription.credits_per_month = new_credits
                        existing_subscription.has_pending_change = False
                        existing_subscription.pending_product_id = None
                        existing_subscription.pending_change_date = None
                        existing_subscription.save()
                        
                        # Get user's credit balance
                        balance, _ = CreditBalance.objects.get_or_create(
                            user=user,
                            defaults={'spectator_balance': 0, 'creator_balance': 0}
                        )
                        current_balance = balance.spectator_balance
                        
                        # Set balance to the subscription amount
                        balance.spectator_balance = new_credits
                        balance.save()
                        
                        # Record the transaction
                        CreditTransaction.objects.create(
                            user=user,
                            amount=new_credits - current_balance,  # Net change
                            transaction_type='credit_subscription',
                            reference_id=transaction_id,
                            metadata={
                                'product_id': new_product_id,
                                'event_id': event_id,
                                'previous_balance': current_balance
                            }
                        )
                        
                        print(f"Reactivated subscription with new product: user_id={user.id}, product={new_product_id}")
                    else:
                        # Create a new subscription with the new product - this should rarely happen
                        # with our "one subscription per user" approach
                        print(f"Creating new subscription for user_id={user.id} with product_id={new_product_id}")
                        subscription = UserSubscription.objects.create(
                            user=user,
                            status='active',
                            revenuecat_id=transaction_id,
                            start_date=datetime.now(timezone.utc),
                            product_id=new_product_id,
                            credits_per_month=new_credits,
                            next_renewal_date=datetime.now(timezone.utc) + timedelta(days=30)
                        )
                        
                        # Get user's credit balance
                        balance, _ = CreditBalance.objects.get_or_create(
                            user=user,
                            defaults={'spectator_balance': 0, 'creator_balance': 0}
                        )
                        current_balance = balance.spectator_balance
                        
                        # Set balance to the new subscription amount
                        balance.spectator_balance = new_credits
                        balance.save()
                        
                        # Record the transaction
                        CreditTransaction.objects.create(
                            user=user,
                            amount=new_credits - current_balance,  # Net change
                            transaction_type='credit_subscription',
                            reference_id=transaction_id,
                            metadata={
                                'product_id': new_product_id,
                                'event_id': event_id,
                                'previous_balance': current_balance
                            }
                        )
                        
                        print(f"Created new subscription with product change: user_id={user.id}, product={new_product_id}")
                
            elif event_type == 'SUBSCRIPTION_PAUSED':
                # Handle subscription pause (Google Play feature)
                try:
                    subscription = UserSubscription.objects.filter(
                        user=user,
                        status='active'
                    ).latest('start_date')  # Get the most recent active subscription
                    
                    # Update status to paused
                    subscription.status = 'paused'
                    subscription.save()
                    
                    print(f"Subscription paused: user_id={user.id}, subscription_id={subscription.id}")
                    
                except UserSubscription.DoesNotExist:
                    print(f"No active subscription found to pause for user_id={user.id}")
                    # For pausing, it doesn't make sense to create a new subscription just to pause it
                    # Just log it and return success
                    return HttpResponse(status=200, content='No active subscription found to pause')
                
            elif event_type == 'SUBSCRIPTION_EXTENDED':
                # Handle subscription extension (e.g., from Google Play compensation)
                try:
                    subscription = UserSubscription.objects.filter(
                        user=user,
                        status='active'
                    ).latest('start_date')  # Get the most recent active subscription
                    
                    # Update expiration time if provided
                    expiration_at_ms = event.get('expiration_at_ms')
                    if expiration_at_ms:
                        expiration_date = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc)
                        subscription.next_renewal_date = expiration_date
                        subscription.save()
                    
                    print(f"Subscription extended: user_id={user.id}, subscription_id={subscription.id}")
                    
                except UserSubscription.DoesNotExist:
                    print(f"No active subscription found to extend for user_id={user.id}")
                    
                    # For extension, we should create a subscription if it doesn't exist
                    if product_id and credits_per_month > 0:
                        subscription = UserSubscription.objects.create(
                            user=user,
                            status='active',
                            revenuecat_id=transaction_id,
                            start_date=datetime.now(timezone.utc),
                            product_id=product_id,
                            credits_per_month=credits_per_month
                        )
                        
                        # Set next_renewal_date if available
                        expiration_at_ms = event.get('expiration_at_ms')
                        if expiration_at_ms:
                            expiration_date = datetime.fromtimestamp(expiration_at_ms / 1000, tz=timezone.utc)
                            subscription.next_renewal_date = expiration_date
                            subscription.save()
                        
                        print(f"Created new subscription for extension: user_id={user.id}, subscription_id={subscription.id}")
                    else:
                        # Cannot create subscription without product details
                        return HttpResponse(status=200, content='Cannot create subscription without product details')
            elif event_type == 'EXPIRATION':
                # Handle subscription expiration
                # This typically happens when a subscription has fully expired after the grace period
                try:
                    # Find the subscription by user id only
                    subscription = UserSubscription.objects.filter(user=user).order_by('-created_at').first()

                    if subscription:
                        print(f"Found subscription for user_id={user.id}: subscription_id={subscription.id}, status={subscription.status}")
                        
                        # Mark the subscription as expired if it's not already
                        if subscription.status != 'expired':
                            old_status = subscription.status
                            subscription.status = 'expired'
                            subscription.end_date = datetime.now(timezone.utc)

                            # Clear any pending change fields when expiring
                            subscription.has_pending_change = False
                            subscription.pending_product_id = None
                            subscription.pending_change_date = None

                            # Get the expiration reason if provided
                            expiration_reason = event.get('expiration_reason')
                            if expiration_reason:
                                subscription.cancel_reason = f"Expired: {expiration_reason}"

                            subscription.save()

                            print(f"Subscription expired: user_id={user.id}, subscription_id={subscription.id}, old_status={old_status}, reason={subscription.cancel_reason}")
                        else:
                            print(f"Subscription already expired: user_id={user.id}, subscription_id={subscription.id}")
                    else:
                        print(f"No subscription found for user_id={user.id}")

                    # Reset credit balance to 0 regardless
                    balance, created = CreditBalance.objects.get_or_create(
                        user=user,
                        defaults={'spectator_balance': 0, 'creator_balance': 0}
                    )

                    if balance.spectator_balance > 0:
                        old_balance = balance.spectator_balance
                        print(f"Resetting credit balance to 0 for user_id={user.id}, previous_balance={old_balance}")
                        
                        CreditTransaction.objects.create(
                            user=user,
                            amount=-old_balance,
                            transaction_type='subscription_expired',
                            reference_id=f"exp_{subscription.id if subscription else 'unknown'}",
                            metadata={
                                'event_id': event_id,
                                'subscription_id': str(subscription.id) if subscription else None,
                                'subscription_product': subscription.product_id if subscription else None,
                                'expiration_reason': subscription.cancel_reason if subscription and subscription.cancel_reason else None,
                                'previous_balance': old_balance,
                                'reset_reason': 'subscription_expiration'
                            }
                        )

                        balance.spectator_balance = 0
                        balance.save()
                        print(f"Credit balance successfully reset to 0 for user_id={user.id}")
                    else:
                        print(f"Credit balance already 0 for user_id={user.id}, no reset needed")

                except Exception as e:
                    print(f"Error processing expiration: {str(e)}")
                    print(f"Continuing to process webhook despite error in EXPIRATION handling")
                
            else:
                # Unknown event type, log it but return success
                print(f"Unknown event type: {event_type}")
        
        return HttpResponse(status=200, content=f'{event_type} event processed successfully')
        
    except json.JSONDecodeError:
        return HttpResponse(status=400, content='Invalid JSON payload')
    except Exception as e:
        # Log the error
        print(f"RevenueCat webhook error: {str(e)}")
        return HttpResponse(status=500, content=str(e)) 