# payments/views.py
import os
from venv import logger
from rest_framework.response import Response
from rest_framework.decorators import api_view
from http import HTTPStatus
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from subscriptions.models import Promotion
from subscriptions.serializers import PromotionSerializer
from users.models import Creator, Spectator, User
from videos.models import Comment, Vision
from .models import Tip, Transaction
from .serializers import TransactionSerializer
import stripe
from rest_framework import status
from users.serializers import UserSerializer, CreatorSerializer
from videos.serializers import CommentSerializer
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.db import models
from .models import CreditBalance, CreditTransaction
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.db.models.expressions import F
from django.db import transaction

# Import credit system views
from .credit_views import (
    get_credit_balance, get_credit_transactions,
    get_user_subscription,
    webhook_revenuecat
)

# Export credit system views
__all__ = [
    'get_credit_balance', 'get_credit_transactions', 
    'send_tip', 'get_user_subscription', 'webhook_revenuecat'
]

@api_view(['GET'])
def get_transactions(request):
    try:
        user = User.objects.get(pk=request.user.pk)
        transactions = Transaction.objects.filter(user=user)
        return Response({'message': 'Successfully retrieved transactions', 'data': TransactionSerializer(transactions, many=True).data})
    except Exception as e:
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def create_transaction(request):
    try:
        user = User.objects.get(pk=request.user.pk)
        transaction_serializer = TransactionSerializer(data=request.data)
        if transaction_serializer.is_valid():
            transaction_serializer.save(user=user)
            return Response({'message': 'Transaction created successfully', 'data': transaction_serializer.data}, status=HTTPStatus.CREATED)
        else:
            return Response({'message': 'There was an error', 'errors': transaction_serializer.errors}, status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_tip(request):
    """
    Send a tip to a creator using credits.
    """
    try:
        amount = int(request.data.get('amount'))  # Amount in credits
        creator_id = request.data.get('creator_id')
        vision_id = request.data.get('vision_id')
        comment_text = request.data.get('comment_text')

        spectator = Spectator.objects.get(user=request.user)
        creator = Creator.objects.get(pk=creator_id)

        # Get or create credit balance for spectator and creator
        spectator_credit_balance, _ = CreditBalance.objects.get_or_create(user=request.user)
        creator_credit_balance, _ = CreditBalance.objects.get_or_create(user=creator.user)

        # Check if spectator has enough credits
        if spectator_credit_balance.spectator_balance < amount:
            return Response({
                'error': True,
                'message': 'insufficient_credits',
                'current_balance': spectator_credit_balance.spectator_balance,
                'required_amount': amount
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create transaction record
        user = User.objects.get(pk=request.user.pk)
        transaction = Transaction.objects.create(
            from_user=user,
            to_user=creator.user,
            amount=amount,
            transaction_type='tip',
            status='pending',
            metadata={
                'tip_message': comment_text,
                'creator_id': creator_id
            }
        )

        try:
            # Deduct credits from spectator
            spectator_credit_balance.deduct_spectator_credits(amount)

            # Add credits to creator
            creator_credit_balance.add_creator_credits(amount)

            # Record credit transactions
            CreditTransaction.objects.create(
                user=user,
                amount=-amount,
                transaction_type='tip',
                reference_id=str(transaction.id),
                metadata={
                    'recipient_id': str(creator.user.id),
                    'tip_message': comment_text
                }
            )

            CreditTransaction.objects.create(
                user=creator.user,
                amount=amount,
                transaction_type='tip',
                reference_id=str(transaction.id),
                metadata={
                    'sender_id': str(request.user.id),
                    'tip_message': comment_text
                }
            )

            # Update transaction status
            transaction.status = 'completed'
            transaction.save()

            if vision_id:
                vision = Vision.objects.get(pk=vision_id)
                
            # Create a Tip record
            tip = Tip.objects.create(
                amount=amount,
                message=comment_text,
                user=user,
                creator=creator,
                transaction=transaction,
                vision=vision
            )
            

            return Response({
                'message': 'success',
                'status': 'tip_sent',
                'tip': {
                    'amount': tip.amount,
                    'message': tip.message,
                    'user': UserSerializer(tip.user).data,
                    'creator': CreatorSerializer(tip.creator).data,
                },
                'remaining_balance': spectator_credit_balance.spectator_balance
            })

        except ValueError as e:
            transaction.status = 'failed'
            transaction.metadata['error'] = str(e)
            transaction.save()
            
            return Response({
                'error': True,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Unexpected error in send_tip")
        return Response(
            {'error': True, 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_payment_method(request):
    """
    Add a payment method to a spectator's Stripe customer account.
    If the spectator doesn't have a Stripe customer ID, one will be created.
    The payment method will be set as the default payment method.
    """
    try:
        spectator = Spectator.objects.get(user=request.user)
        payment_method_id = request.data.get('card_token')

        logger.info(f"Adding payment method for user {request.user.username} with payment_method_id {payment_method_id}")

        if not payment_method_id:
            logger.error("Payment method ID missing from request")
            return Response({'error': 'Payment method ID is required'}, status=HTTPStatus.BAD_REQUEST)

        try:
            # Create or retrieve Stripe customer on the platform account
            if not spectator.stripe_customer_id:
                logger.info(f"Creating new Stripe customer for user {request.user.username}")
                
                # Create customer first
                customer = stripe.Customer.create(
                    email=spectator.user.email,
                    description=f"Customer for {spectator.user.username}",
                    metadata={
                        'user_id': str(spectator.user.id),
                        'username': spectator.user.username
                    }
                )
                
                logger.info(f"Created Stripe customer {customer.id} for user {request.user.username}")
                
                # Attach payment method to customer
                payment_method = stripe.PaymentMethod.attach(
                    payment_method_id,
                    customer=customer.id,
                )
                
                # Set as default payment method
                stripe.Customer.modify(
                    customer.id,
                    invoice_settings={
                        'default_payment_method': payment_method_id
                    }
                )
                
                spectator.stripe_customer_id = customer.id
                spectator.save()
                
                logger.info(f"Set payment method {payment_method_id} as default for customer {customer.id}")
            else:
                logger.info(f"Adding payment method to existing customer {spectator.stripe_customer_id}")
                
                # For existing customers, attach the payment method
                payment_method = stripe.PaymentMethod.attach(
                    payment_method_id,
                    customer=spectator.stripe_customer_id,
                )
                
                # Set it as the default payment method
                stripe.Customer.modify(
                    spectator.stripe_customer_id,
                    invoice_settings={
                        'default_payment_method': payment_method_id
                    }
                )
                
                logger.info(f"Set payment method {payment_method_id} as default for existing customer {spectator.stripe_customer_id}")

            # Retrieve the updated payment method to confirm it's attached
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            
            # Verify customer has the payment method
            customer = stripe.Customer.retrieve(spectator.stripe_customer_id)
            payment_methods = stripe.PaymentMethod.list(
                customer=spectator.stripe_customer_id,
                type="card"
            )
            
            logger.info(f"Customer {spectator.stripe_customer_id} now has {len(payment_methods.data)} payment methods")

            return Response({
                'message': 'Payment method added successfully',
                'customer_id': spectator.stripe_customer_id,
                'payment_method_id': payment_method_id,
                'card': {
                    'brand': payment_method.card.brand,
                    'last4': payment_method.card.last4,
                    'exp_month': payment_method.card.exp_month,
                    'exp_year': payment_method.card.exp_year
                }
            }, status=HTTPStatus.OK)
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error while adding payment method: {str(e)}")
            return Response(
                {'error': f'Error adding payment method: {str(e)}'},
                status=HTTPStatus.BAD_REQUEST
            )
            
    except Exception as e:
        logger.exception("Unexpected error in add_payment_method")
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_payment_methods(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        
        if not spectator.stripe_customer_id:
            return Response({'error': 'No payment methods found'}, status=status.HTTP_404_NOT_FOUND)
        
        payment_methods = stripe.PaymentMethod.list(
            customer=spectator.stripe_customer_id,
            type="card"
        )
        
        # Get customer to check default payment method
        customer = stripe.Customer.retrieve(spectator.stripe_customer_id)
        default_payment_method = customer.invoice_settings.default_payment_method
        
        formatted_methods = [{
            'id': method.id,
            'brand': method.card.brand,
            'last4': method.card.last4,
            'exp_month': method.card.exp_month,
            'exp_year': method.card.exp_year,
            'is_default': method.id == default_payment_method
        } for method in payment_methods.data]

        print(formatted_methods)
        
        return Response({
            'payment_methods': formatted_methods
        }, status=status.HTTP_200_OK)
    
    except Spectator.DoesNotExist:
        return Response({'error': 'Spectator not found'}, status=status.HTTP_404_NOT_FOUND)
    except stripe.error.StripeError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_default_payment_method(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        payment_method_id = str(request.data.get('payment_method_id', '')).strip()  # Ensure it's a string
        
        if not payment_method_id:
            return Response({'error': 'Payment method ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not spectator.stripe_customer_id:
            return Response({'error': 'No Stripe customer found for this user'}, status=status.HTTP_404_NOT_FOUND)
        
        # Attach the payment method to the customer if it's not already attached
        stripe.PaymentMethod.attach(
            payment_method_id,
            customer=spectator.stripe_customer_id,
        )
        
        # Set the default payment method on the customer
        stripe.Customer.modify(
            spectator.stripe_customer_id,
            invoice_settings={
                'default_payment_method': payment_method_id
            }
        )

        # Log the update
        logger.info(f"Default payment method updated for user {request.user.username} with payment method {payment_method_id}")
        
        # Get updated list of payment methods from Stripe
        payment_methods = stripe.PaymentMethod.list(
            customer=spectator.stripe_customer_id,
            type="card"
        )
        
        formatted_methods = [{
            'id': method.id,
            'brand': method.card.brand,
            'last4': method.card.last4,
            'exp_month': method.card.exp_month,
            'exp_year': method.card.exp_year,
            'is_default': method.id == payment_method_id
        } for method in payment_methods.data]
        
        # Print the updated list of payment methods
        print(formatted_methods)
        
        return Response({
            'message': 'Default payment method updated successfully',
            'payment_method_id': payment_method_id
        }, status=status.HTTP_200_OK)
    
    except Spectator.DoesNotExist:
        return Response({'error': 'Spectator not found'}, status=status.HTTP_404_NOT_FOUND)
    except stripe.error.StripeError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.info(f"Error updating default payment method: {e}")
        logger.exception("Unexpected error while updating default payment method.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_payment_method(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        payment_method_id = request.data.get('payment_method_id')
        
        if not payment_method_id:
            return Response({'error': 'Payment method ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not spectator.stripe_customer_id:
            return Response({'error': 'No Stripe customer found for this user'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get the payment method to check if it belongs to the customer
        payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
        if payment_method.customer != spectator.stripe_customer_id:
            return Response({'error': 'Payment method does not belong to this customer'}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if it's the default payment method
        customer = stripe.Customer.retrieve(spectator.stripe_customer_id)
        is_default = customer.invoice_settings.default_payment_method == payment_method_id
        
        # If it's the default payment method, we need to unset it first
        if is_default:
            stripe.Customer.modify(
                spectator.stripe_customer_id,
                invoice_settings={'default_payment_method': None}
            )
        
        # Detach the payment method
        stripe.PaymentMethod.detach(payment_method_id)
        
        # Log the deletion
        logger.info(f"Payment method {payment_method_id} deleted for user {request.user.username}")
        
        return Response({
            'message': 'Payment method deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Spectator.DoesNotExist:
        return Response({'error': 'Spectator not found'}, status=status.HTTP_404_NOT_FOUND)
    except stripe.error.StripeError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error while deleting payment method.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_balance(request):
    """
    Retrieve the available credit balance for a creator.
    Shows both total balance and available balance (credits older than 31 days).
    """
    try:
        creator = Creator.objects.get(user=request.user)
        credit_balance, _ = CreditBalance.objects.get_or_create(
            user=creator.user,
            defaults={'spectator_balance': 0, 'creator_balance': 0}
        )
        
        # Get pending credits (less than 31 days old)
        pending_credits = CreditTransaction.objects.filter(
            user=creator.user,
            transaction_type__in=['tip', 'subscription', 'vision_request', 'subscription_renewal'],
            created_at__gt=timezone.now() - timedelta(days=31),
            amount__gt=0  # Only positive transactions
        ).aggregate(models.Sum('amount'))['amount__sum'] or 0
        
        # Get pending withdrawals
        pending_withdrawals = Transaction.objects.filter(
            from_user=creator.user,
            transaction_type='payout',
            status='pending'
        ).aggregate(models.Sum('amount'))['amount__sum'] or 0
        
        # Calculate available balance (total balance - pending credits)
        total_balance = credit_balance.creator_balance
        available_balance = total_balance - pending_credits - pending_withdrawals
        
        return Response({
            'total_balance': total_balance,
            'available': available_balance,
            'pending': pending_credits,
            'pending_withdrawals': pending_withdrawals,
            'holding_period_days': 31
        }, status=status.HTTP_200_OK)
        
    except Creator.DoesNotExist:
        return Response(
            {'error': 'Creator account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("Unexpected error retrieving creator balance")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def withdraw_earnings(request):
    """
    Create a ledger entry for withdrawal of available earnings, transfer funds to the creator's
    Stripe Connect account, and provide a link to Stripe Express dashboard for the user to manage their payouts.
    Only earnings older than 31 days can be withdrawn.
    Minimum withdrawal amount is $50, which requires Stripe Connect onboarding.
    """
    try:
        dollar_amount = float(request.data.get('amount', 0))
        credit_amount = int(dollar_amount * 10)
        
        creator = Creator.objects.get(user=request.user)
        credit_balance = CreditBalance.objects.get(user=creator.user)
        
        # Calculate available earnings (older than 31 days)
        pending_credits = CreditTransaction.objects.filter(
            user=creator.user,
            transaction_type__in=['tip', 'subscription', 'vision_request', 'subscription_renewal'],
            created_at__gt=timezone.now() - timedelta(days=31),
            amount__gt=0  # Only positive transactions
        ).aggregate(models.Sum('amount'))['amount__sum'] or 0
        
        # Get pending withdrawals
        pending_withdrawals = Transaction.objects.filter(
            from_user=creator.user,
            transaction_type='payout',
            status='pending'
        ).aggregate(models.Sum('amount'))['amount__sum'] or 0
        
        available_for_withdrawal = credit_balance.creator_balance - pending_credits - pending_withdrawals

        verification_threshold = 50
        
        # Check minimum withdrawal amount
        if dollar_amount < float(verification_threshold):
            return Response(
                {
                    'error': f'Minimum withdrawal amount is ${verification_threshold}',
                    'minimum_amount': float(verification_threshold)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if amount exceeds available earnings
        if credit_amount > available_for_withdrawal:
            return Response({
                'error': 'Insufficient available earnings',
                'available_amount': available_for_withdrawal,
                'requested_amount': credit_amount,
                'pending_period': '31 days'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure Stripe Connect account exists and is verified
        if not creator.stripe_connect_id:
            try:
                account = stripe.Account.create(
                    type='express',
                    country='US',
                    email=request.user.email,
                    capabilities={
                        'card_payments': {'requested': True},
                        'transfers': {'requested': True},
                    },
                )
                creator.stripe_connect_id = account.id
                creator.save()
            except stripe.error.StripeError as e:
                logger.error(f"Error creating Stripe Connect account: {str(e)}")
                return Response(
                    {'error': f'Error setting up payout account: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Check if onboarding is needed
        if not creator.stripe_connect_onboarding_completed:
            account = stripe.Account.retrieve(creator.stripe_connect_id)
            
            if account.details_submitted:
                creator.stripe_connect_onboarding_completed = True
                creator.save()
            else:
                account_link = stripe.AccountLink.create(
                    account=creator.stripe_connect_id,
                    refresh_url=f'{settings.FRONTEND_URL}/creator/connect/refresh',
                    return_url=f'{settings.FRONTEND_URL}/creator/connect/return',
                    type='account_onboarding',
                )
                
                return Response(
                    {
                        'needs_onboarding': True,
                        'message': 'Please complete account verification to withdraw your earnings',
                        'onboarding_url': account_link.url
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        with transaction.atomic():
            # Create withdrawal transaction
            withdrawal_tx = Transaction.objects.create(
                from_user=creator.user,
                to_user=creator.user,  # Self-transfer for withdrawal
                amount=credit_amount,
                transaction_type='payout',
                status='pending',
                metadata={
                    'withdrawal_amount': str(credit_amount),
                    'available_balance_before': str(available_for_withdrawal)
                }
            )

            try:
                # For cross-border transfers, use PaymentIntent with on_behalf_of parameter 
                # to specify the connected account as the settlement merchant
                
                platform_fee = 0.8 # 20% fee
                payout_amount = int(dollar_amount * platform_fee * 100)
                
                # Create a payment intent with the connected account as the settlement merchant
                # This allows cross-region transfers by making the connected account the merchant of record
                payment_intent = stripe.PaymentIntent.create(
                    amount=payout_amount,  # Full amount in cents
                    currency='usd',
                    payment_method_types=['card'],
                    capture_method='manual',  # We'll capture it manually
                    on_behalf_of=creator.stripe_connect_id,  # This makes connected account the settlement merchant
                    application_fee_amount=0,
                    transfer_data={
                        'destination': creator.stripe_connect_id,
                    },
                    confirm=True,  # Try to confirm immediately
                    payment_method=os.environ.get('STRIPE_PLATFORM_PAYMENT_METHOD'),
                    description=f"Payout to {creator.user.username} - ID: {withdrawal_tx.id}"
                )
                
                # Capture the payment to complete the transfer
                capture = stripe.PaymentIntent.capture(payment_intent.id)
                
                # Deduct from creator's balance
                credit_balance.deduct_creator_credits(credit_amount)
                
                # Record the credit transaction
                credit_tx = CreditTransaction.objects.create(
                    user=creator.user,
                    amount=-credit_amount,
                    transaction_type='payout',
                    reference_id=payment_intent.id,
                    metadata={
                        'stripe_payment_intent_id': payment_intent.id,
                        'withdrawal_tx_id': str(withdrawal_tx.id),
                        'payout_amount': payout_amount / 100  # Convert back to dollars
                    }
                )
                
                # Update transaction status
                withdrawal_tx.status = 'completed'
                withdrawal_tx.stripe_payment_intent_id = payment_intent.id
                withdrawal_tx.stripe_transfer_id = None  # Clear the transfer ID since we're using payment intent
                withdrawal_tx.save()
                
                return Response(
                    {
                        'message': 'Withdrawal successful',
                        'payout_id': payment_intent.id,
                        'details': {
                            'transaction_id': withdrawal_tx.id,
                            'credit_transaction_id': credit_tx.id,
                            'stripe_payment_intent_id': payment_intent.id,
                            'remaining_balance': credit_balance.creator_balance,
                            'remaining_available': available_for_withdrawal - credit_amount,
                            'withdrawal_amount': credit_amount
                        }
                    },
                    status=status.HTTP_200_OK
                )
            except stripe.error.StripeError as e:
                try:
                    # Update transaction status
                    withdrawal_tx.status = 'failed'
                    withdrawal_tx.save()
                except Exception:
                    pass

                logger.error(f"Stripe Error during withdrawal: {str(e)}")
                return Response(
                    {
                        'error': f'Error processing withdrawal: {str(e)}',
                        'transaction_id': withdrawal_tx.id, 
                        'remaining_balance': credit_balance.creator_balance,
                        'remaining_available': available_for_withdrawal,
                        'withdrawal_amount': credit_amount,
                        'stripe_error': str(e)
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
                
    except Creator.DoesNotExist:
        return Response(
            {'error': 'Creator account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {str(e)}")
        return Response(
            {'error': f'Stripe error: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.exception("Unexpected error processing withdrawal")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def enable_monetization(request):
    """
    Enable monetization for a creator by initiating Stripe Connect onboarding.
    """
    try:
        creator = Creator.objects.get(user=request.user)
        
        # Check if already enabled
        if creator.can_accept_payments():
            return Response({
                'message': 'Monetization already enabled',
                'status': 'active'
            }, status=status.HTTP_200_OK)

        # Create Stripe Connect account if doesn't exist
        if not creator.stripe_connect_id:
            try:
                account = stripe.Account.create(
                    type='express',
                    country='US',
                    email=request.user.email,
                    capabilities={
                        'card_payments': {'requested': True},
                        'transfers': {'requested': True},
                    },
                )
                creator.stripe_connect_id = account.id
                creator.monetization_status = 'onboarding'
                creator.save()
            except stripe.error.StripeError as e:
                logger.error(f"Error creating Stripe Connect account: {str(e)}")
                return Response(
                    {'error': f'Error setting up monetization: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Create/get account link for onboarding
        try:
            account_link = stripe.AccountLink.create(
                account=creator.stripe_connect_id,
                refresh_url=f'{settings.FRONTEND_URL}/creator/connect/refresh',
                return_url=f'{settings.FRONTEND_URL}/creator/connect/return',
                type='account_onboarding',
            )
            
            return Response({
                'message': 'Monetization setup initiated',
                'onboarding_url': account_link.url,
                'status': creator.monetization_status
            }, status=status.HTTP_200_OK)
            
        except stripe.error.StripeError as e:
            logger.error(f"Error creating account link: {str(e)}")
            return Response(
                {'error': f'Error generating onboarding link: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    except Creator.DoesNotExist:
        return Response(
            {'error': 'Creator account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("Unexpected error enabling monetization")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_monetization_status(request):
    """
    Check the current monetization status of a creator.
    """
    try:
        creator = Creator.objects.get(user=request.user)
        
        if creator.stripe_connect_id:
            # Check Stripe account status
            account = stripe.Account.retrieve(creator.stripe_connect_id)
            
            if account.details_submitted and not creator.stripe_connect_onboarding_completed:
                creator.stripe_connect_onboarding_completed = True
                creator.monetization_status = 'active'
                creator.can_receive_payments = True
                creator.save()
            
            return Response({
                'monetization_status': creator.monetization_status,
                'can_accept_payments': creator.can_accept_payments(),
                'details_submitted': account.details_submitted if hasattr(account, 'details_submitted') else False,
                'charges_enabled': account.charges_enabled if hasattr(account, 'charges_enabled') else False,
                'payouts_enabled': account.payouts_enabled if hasattr(account, 'payouts_enabled') else False
            }, status=status.HTTP_200_OK)
            
        return Response({
            'monetization_status': creator.monetization_status,
            'can_accept_payments': creator.can_accept_payments()
        }, status=status.HTTP_200_OK)
        
    except Creator.DoesNotExist:
        return Response(
            {'error': 'Creator account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        logger.error(f"Error checking Stripe account: {str(e)}")
        return Response(
            {'error': f'Error checking monetization status: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.exception("Unexpected error checking monetization status")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_revenuecat_uuid(request):
    """Update the RevenueCat UUID for the authenticated user"""
    try:
        revenuecat_uuid = request.data.get('revenuecat_uuid')
        
        if not revenuecat_uuid:
            return Response(
                {'error': 'RevenueCat UUID is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Check if this UUID is already used by another user
        if User.objects.filter(revenuecat_uuid=revenuecat_uuid).exclude(pk=request.user.pk).exists():
            return Response(
                {'error': 'This RevenueCat UUID is already associated with another account'},
                status=status.HTTP_409_CONFLICT
            )
        
        user = User.objects.get(pk=request.user.pk)
        user.revenuecat_uuid = revenuecat_uuid
        user.save()
        
        return Response({
            'success': True,
            'message': 'RevenueCat UUID updated successfully'
        })
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_stripe_dashboard_url(request):
    """
    Generate and return a URL to access the creator's Stripe Express dashboard.
    Requires the user to have a Creator account with a connected Stripe account.
    """
    try:
        creator = Creator.objects.get(user=request.user)
        
        # Check if the creator has a Stripe Connect account
        if not creator.stripe_connect_id:
            return Response(
                {'error': 'You do not have a connected Stripe account yet'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if onboarding is needed
        if not creator.stripe_connect_onboarding_completed:
            account = stripe.Account.retrieve(creator.stripe_connect_id)
            
            if account.details_submitted:
                creator.stripe_connect_onboarding_completed = True
                creator.save()
            else:
                account_link = stripe.AccountLink.create(
                    account=creator.stripe_connect_id,
                    refresh_url=f'{settings.FRONTEND_URL}/creator/connect/refresh',
                    return_url=f'{settings.FRONTEND_URL}/creator/connect/return',
                    type='account_onboarding',
                )
                
                return Response(
                    {
                        'needs_onboarding': True,
                        'message': 'Please complete account verification first',
                        'onboarding_url': account_link.url
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        # Create a login link to Stripe Express dashboard
        try:
            login_link = stripe.Account.create_login_link(
                creator.stripe_connect_id
            )
            
            return Response({
                'dashboard_url': login_link.url
            }, status=status.HTTP_200_OK)
            
        except stripe.error.StripeError as e:
            logger.error(f"Error creating Stripe login link: {str(e)}")
            return Response(
                {'error': f'Could not generate Stripe dashboard link: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
                
    except Creator.DoesNotExist:
        return Response(
            {'error': 'Creator account not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {str(e)}")
        return Response(
            {'error': f'Stripe error: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.exception("Unexpected error generating dashboard URL")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
