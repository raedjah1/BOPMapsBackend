# subscriptions/views.py
from datetime import datetime, timedelta
import os
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from http import HTTPStatus
from django.utils import timezone
import stripe.error
from payments.models import CreditBalance, CreditTransaction, Transaction
from pov_backend import settings
from subscriptions.serializers import PromotionSerializer
from users.serializers import CreatorSerializer, SpectatorSerializer
from .models import Promotion, Subscription
from users.models import Spectator, Creator, User
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
import stripe
from users.models import ActivityItem, ActivityEvent, UserActivity
from users.activity_manager import ActivityManager
from django.db.models import Q, F
from django.db import transaction as db_transaction

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


stripe.api_key =  os.environ.get('STRIPE_SECRET_KEY')

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def subscribe(request, pk):
    """
    Subscribe to a creator using credits.
    """
    try:
        spectator = Spectator.objects.get(user=request.user)
        creator = Creator.objects.get(pk=pk)
        subscription_type = request.data.get('subscription_type', 'free')
        print(subscription_type)

        # Check if creator exists
        if not creator:
            return Response(
                {'error': True, 'message': 'creator_not_found'},
                status=HTTPStatus.NOT_FOUND
            )

        # Check for any existing subscription, including inactive ones
        existing_subscription = Subscription.objects.filter(
            spectator=spectator,
            creator=creator
        ).first()
        
        # If there's an active subscription
        if existing_subscription and existing_subscription.is_active:
            if existing_subscription.subscription_type == 'paid':
                print(existing_subscription.subscription_type)
                return Response(
                    {'error': True, 'message': 'already_subscribed'},
                    status=HTTPStatus.BAD_REQUEST
                )
            elif subscription_type == 'free':
                print(subscription_type)
                return Response(
                    {'error': True, 'message': 'already_subscribed'},
                    status=HTTPStatus.BAD_REQUEST
                )
        
        if subscription_type == 'free':
            # If there's an inactive subscription, reactivate it
            if existing_subscription:
                existing_subscription.is_active = True
                existing_subscription.end_date = None
                existing_subscription.save()
                subscription = existing_subscription
            else:
                # Create new free subscription
                subscription = Subscription.objects.create(
                    spectator=spectator,
                    creator=creator,
                    subscription_type='free',
                    start_date=timezone.now()
                )
            
            # Add the creator to the spectator's subscriptions
            spectator.subscriptions.add(creator)
            spectator.save()
            
            # Increment the creator's subscriber count
            creator.subscriber_count += 1
            creator.save()

            # Create activity notifications
            ActivityManager.create_activity_item(
                creator=creator,
                text=f"Subscribed to {creator.user.username}",
                user=User.objects.get(pk=request.user.pk),
                image_url=creator.user.profile_picture_url
            )

            ActivityManager.create_activity_and_notify(
                actor=User.objects.get(pk=request.user.pk),
                action_type='subscribe',
                target_id=creator.pk,
                target_type='creator',
                notify_user=creator.user,
                notification_title="New Subscriber",
                notification_body=f"{request.user.username} subscribed to your channel"
            )

            return Response({
                'message': 'success',
                'subscriber_count': creator.subscriber_count,
                'subscription_type': 'free'
            })

        else:
            # Get credit balance for spectator and creator
            spectator_credit_balance, _ = CreditBalance.objects.get_or_create(user=request.user)
            creator_credit_balance, _ = CreditBalance.objects.get_or_create(user=creator.user)
            original_price = creator.subscription_price
            final_price = original_price
            
            # Initialize promotion to None outside of the if/else blocks
            promotion = None

            # If there's an existing subscription with an upcoming end date, set final price to 0
            if existing_subscription and existing_subscription.end_date and existing_subscription.end_date > timezone.now():
                final_price = 0
                original_price = 0
            else:
                # Check for and apply promotion if valid
                try:
                    promotion = Promotion.objects.get(
                        creator=creator,
                        is_active=True,
                        end_date__gt=timezone.now()  # Make sure promotion hasn't expired
                    )
                    
                    # Check if promotion has reached its redemption limit
                    if promotion.redemption_limit and promotion.redemption_count >= promotion.redemption_limit:
                        promotion = None
                    elif promotion.is_valid():
                        if promotion.promotion_type == 'free_trial':
                            final_price = 0
                        else:  # discount type
                            discount_amount = (promotion.promotion_amount / 100) * original_price
                            final_price = original_price - discount_amount
                            final_price = max(0, final_price)  # Ensure price doesn't go negative
                except Promotion.DoesNotExist:
                    promotion = None

                # Check if spectator has enough credits (only if final_price > 0)
                if final_price > 0 and spectator_credit_balance.spectator_balance < final_price:
                    return Response({
                        'error': True,
                        'message': 'insufficient_credits',
                        'current_balance': spectator_credit_balance.spectator_balance,
                        'required_amount': float(final_price),
                        'original_price': float(original_price),
                        'promotion_discount': float(original_price - final_price) if promotion else 0
                    }, status=HTTPStatus.BAD_REQUEST)

            # Create transaction record only if there's a cost
            transaction = None
            if final_price > 0:
                user = User.objects.get(pk=request.user.pk)
                transaction = Transaction.objects.create(
                    from_user=user,
                    to_user=creator.user,
                    amount=final_price,
                    transaction_type='subscription',
                    status='pending',
                    metadata={
                        'subscription_type': 'paid',
                        'creator_id': str(creator.pk),
                        'original_price': str(float(original_price)),
                        'promotion_applied': bool(promotion),
                        'promotion_id': str(promotion.pk) if promotion else None,
                        'promotion_type': promotion.promotion_type if promotion else None,
                        'promotion_amount': str(float(promotion.promotion_amount)) if promotion else None,
                        'final_price': str(float(final_price))
                    }
                )

            try:
                # Handle subscription creation/renewal
                if existing_subscription:
                    # Reactivate and update existing subscription
                    existing_subscription.subscription_type = 'paid'
                    existing_subscription.next_payment_date = timezone.now() + timedelta(days=30)
                    existing_subscription.end_date = None
                    existing_subscription.is_active = True
                    existing_subscription.promotion = promotion if not existing_subscription.end_date else None
                    existing_subscription.transaction = transaction
                    existing_subscription.save()
                    subscription = existing_subscription
                else:
                    # Create new subscription
                    subscription = Subscription.objects.create(
                        spectator=spectator,
                        creator=creator,
                        subscription_type='paid',
                        start_date=timezone.now(),
                        next_payment_date=timezone.now() + timedelta(days=30),
                        promotion=promotion,
                        transaction=transaction
                    )

                # Process credit transaction only if there's a cost
                if final_price > 0:
                    try:
                        # Convert final_price to integer for credit operations
                        credit_amount = int(float(final_price))
                        
                        # Wrap all credit operations in a transaction using select_for_update to lock the rows
                        with db_transaction.atomic():
                            scb = CreditBalance.objects.select_for_update().get(user=request.user)
                            ccb = CreditBalance.objects.select_for_update().get(user=creator.user)
                            
                            # Print initial balances from locked rows
                            print(f"[Atomic] Initial spectator balance: {scb.spectator_balance}")
                            print(f"[Atomic] Initial creator balance: {ccb.creator_balance}")
                            print(f"[Atomic] Credit amount to transfer: {credit_amount}")
                            
                            # Deduct credits from spectator
                            scb.deduct_spectator_credits(credit_amount)
                            scb.refresh_from_db()
                            print(f"[Atomic] After deduction - Spectator balance: {scb.spectator_balance}")
                            
                            # Add credits to creator
                            ccb.add_creator_credits(credit_amount)
                            ccb.refresh_from_db()
                            print(f"[Atomic] After addition - Creator balance: {ccb.creator_balance}")
                            
                            # Record credit transactions with explicit amounts
                            spectator_tx = CreditTransaction.objects.create(
                                user=user,
                                amount=-credit_amount,  # Negative for deduction
                                transaction_type='subscription',
                                reference_id=str(transaction.id),
                                metadata={
                                    'creator_id': str(creator.pk),
                                    'promotion_applied': bool(promotion),
                                    'original_price': str(float(original_price)),
                                    'final_price': str(float(final_price)),
                                    'balance_after': scb.spectator_balance
                                }
                            )

                            creator_tx = CreditTransaction.objects.create(
                                user=creator.user,
                                amount=credit_amount,  # Positive for addition
                                transaction_type='subscription',
                                reference_id=str(transaction.id),
                                metadata={
                                    'subscriber_id': str(request.user.pk),
                                    'promotion_applied': bool(promotion),
                                    'original_price': str(float(original_price)),
                                    'final_price': str(float(final_price)),
                                    'balance_after': ccb.creator_balance
                                }
                            )
                            
                            # Explicitly save the updated balances
                            scb.save()
                            ccb.save()

                        # End of atomic block; re-read balances
                        spectator_credit_balance.refresh_from_db()
                        creator_credit_balance.refresh_from_db()
                        print(f"\nFinal balances after transaction:")
                        print(f"Spectator balance: {spectator_credit_balance.spectator_balance}")
                        print(f"Creator balance: {creator_credit_balance.creator_balance}")
                        print(f"Transaction IDs: Spectator {spectator_tx.id}, Creator {creator_tx.id}")
                        
                    except ValueError as e:
                        print(f"ValueError in credit transaction: {str(e)}")
                        raise ValueError(f"Error processing credit transaction: {str(e)}")
                    except Exception as e:
                        print(f"Unexpected error in credit transaction: {str(e)}")
                        raise ValueError(f"Unexpected error in credit transaction: {str(e)}")

                # If promotion was used, increment its redemption count
                if promotion:
                    promotion.redemption_count = F('redemption_count') + 1
                    promotion.save()

                # Update transaction status
                if transaction:
                    transaction.status = 'completed'
                    transaction.save()
                
                # Add the creator to the spectator's subscriptions
                spectator.subscriptions.add(creator)
                spectator.save()
                
                # Increment the creator's subscriber count
                creator.subscriber_count += 1
                creator.save()

                # Create activity notifications
                creator_user = User.objects.get(pk=creator.user.pk)
                subscriber_user = User.objects.get(pk=request.user.pk)

                ActivityManager.create_activity_item(
                    creator=creator,
                    text=f"Subscribed to {creator_user.username}",
                    user=subscriber_user,
                    image_url=creator_user.profile_picture_url
                )

                ActivityManager.create_activity_and_notify(
                    actor=subscriber_user,
                    action_type='subscribe',
                    target_id=creator.pk,
                    target_type='creator',
                    notify_user=creator_user,
                    notification_title="New Subscriber",
                    notification_body=f"{subscriber_user.username} subscribed to your channel"
                )

                return Response({
                    'message': 'success',
                    'subscription_id': subscription.pk,
                    'subscriber_count': creator.subscriber_count,
                    'remaining_balance': spectator_credit_balance.spectator_balance,
                    'original_price': float(original_price),
                    'final_price': float(final_price),
                    'promotion_applied': bool(promotion),
                    'promotion_type': promotion.promotion_type if promotion else None,
                    'promotion_amount': float(promotion.promotion_amount) if promotion else None,
                    'next_payment_date': subscription.next_payment_date
                })

            except ValueError as e:
                # Update transaction status
                transaction.status = 'failed'
                transaction.metadata['error'] = str(e)
                transaction.save()

                print(e)
                
                return Response({
                    'error': True,
                    'message': str(e)
                }, status=HTTPStatus.BAD_REQUEST)
                
    except Exception as e:
        print(e)
        return Response({
            'error': True,
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_subscriptions(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        return Response({'message': 'Successfully retrieved subscriptions', 'data': CreatorSerializer(spectator.subscriptions, many=True).data})
    except Exception as e:
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_card(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        
        # Create or retrieve Stripe customer
        if not spectator.stripe_customer_id:
            customer = stripe.Customer.create(
                email=spectator.user.email,
            )
            spectator.stripe_customer_id = customer.id
            spectator.save()
        else:
            customer = stripe.Customer.retrieve(spectator.stripe_customer_id)

        # Create a SetupIntent
        setup_intent = stripe.SetupIntent.create(
            customer=customer.id,
            automatic_payment_methods={
                'enabled': True,
            },
        )

        return Response({
            'client_secret': setup_intent.client_secret,
            'message': 'SetupIntent created successfully'
        }, status=HTTPStatus.OK)
    except stripe.error.StripeError as e:
        return Response({'error': True, 'message': str(e)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        return Response({'error': True, 'message': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_creator_price(request):
    try:
        creator = Creator.objects.get(user=request.user)
        new_price = int(request.data.get('price'))  # Price in credits
        
        if not new_price:
            print("Missing price")
            return Response({'error': 'missing_price'}, status=HTTPStatus.BAD_REQUEST)
        
        if new_price < 0:
            return Response({'error': 'invalid_price'}, status=HTTPStatus.BAD_REQUEST)
        
        # Update the creator's subscription price
        creator.subscription_price = new_price
        creator.save()

        return Response({
            'message': 'Subscription price updated successfully',
            'new_price': new_price
        }, status=HTTPStatus.OK)
        
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=HTTPStatus.NOT_FOUND)
    except ValueError:
        return Response({'error': 'Invalid price format'}, status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

def check_and_process_subscription(subscription):
    """
    Helper function to check and process expired subscriptions
    Returns True if subscription was processed/deleted
    """
    if (subscription.end_date and 
        subscription.end_date <= timezone.now() and subscription.is_active == False):
        
        try:
            # Delete the subscription
            subscription.delete()
            return True

        except Exception as e:
            print(f"Error processing subscription {subscription.id}: {str(e)}")
            
    return False

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_subscription_status(request, creator_id):
    creator = get_object_or_404(Creator, pk=creator_id)
    
    try:
        spectator = Spectator.objects.get(user=request.user)
        subscription = Subscription.objects.filter(
            spectator=spectator, 
            creator=creator
        ).first()

        # Check if user has set a reminder for this creator
        is_reminded = creator in spectator.reminder_creators.all()
        
        # Check if user is blocked by creator
        is_blocked = request.user in creator.user.blocked_users.all()

        if subscription:
            # Check if subscription has expired
            if check_and_process_subscription(subscription):
                return Response({
                    'is_subscribed': False,
                    'is_reminded': is_reminded,
                    'is_blocked': is_blocked,
                    'creator_id': creator_id,
                    'creator_username': creator.user.username,
                    'subscription_type': subscription.subscription_type,
                    'end_date': subscription.end_date
                })

            response_data = {
                'is_subscribed': subscription.has_not_expired and subscription.is_active,
                'is_reminded': is_reminded,
                'is_blocked': is_blocked,
                'creator_id': creator_id,
                'creator_username': creator.user.username,
                'subscription_type': subscription.subscription_type,
                'end_date': subscription.end_date
            }
            
            if subscription.end_date:
                response_data['end_date'] = subscription.end_date
            
            return Response(response_data)
        
        return Response({
            'is_subscribed': False,
            'is_reminded': is_reminded,
            'is_blocked': is_blocked,
            'creator_id': creator_id,
            'creator_username': creator.user.username
        })
    
    except Spectator.DoesNotExist:
        # Check if user is blocked by creator even if spectator doesn't exist
        is_blocked = request.user in creator.user.blocked_users.all()
        
        return Response({
            'is_subscribed': False,
            'is_reminded': False,
            'is_blocked': is_blocked,
            'creator_id': creator_id,
            'creator_username': creator.user.username
        })

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def unsubscribe(request, pk):
    try:
        spectator = Spectator.objects.get(user=request.user)
        creator = Creator.objects.get(pk=pk)

        # Check if the user is subscribed
        subscription = Subscription.objects.filter(spectator=spectator, creator=creator).first()
        if not subscription:
            print("Not subscribed")
            return Response({
                'error': True,
                'message': 'not_subscribed'
            }, status=HTTPStatus.BAD_REQUEST)

        # For paid subscriptions, set end date to current subscription period end
        if subscription.subscription_type == 'paid':
            subscription.end_date = subscription.next_payment_date or timezone.now()
            subscription.is_active = False
            subscription.save()
        else:
            # For free subscriptions, delete the record
            subscription.delete()

        # Remove the creator from the spectator's subscriptions
        spectator.subscriptions.remove(creator)

        # Decrement the creator's subscriber count
        creator.subscriber_count = max(0, creator.subscriber_count - 1)
        creator.save()
        spectator.save()

        return Response({
            'message': 'success',
            'subscriber_count': creator.subscriber_count,
            'end_date': subscription.end_date if subscription.subscription_type == 'paid' else None
        })

    except Spectator.DoesNotExist:
        return Response({
            'error': True,
            'message': 'spectator_not_found'
        }, status=HTTPStatus.NOT_FOUND)
    except Creator.DoesNotExist:
        return Response({
            'error': True,
            'message': 'creator_not_found'
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        print(e)
        return Response({
            'error': True,
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_promotion(request):
    try:
        creator = Creator.objects.get(user=request.user)
        
        promotion_type = request.data.get('promotionType')
        end_date = request.data.get('endDate')
        redemption_limit = request.data.get('redemptionLimit')

        # Handle redemption limit
        if redemption_limit == 'Unlimited' or redemption_limit == '':
            redemption_limit = None
        else:
            try:
                redemption_limit = int(redemption_limit)
                if redemption_limit < 0:
                    redemption_limit = None
            except (ValueError, TypeError):
                return Response({
                    'error': True,
                    'message': 'Invalid redemption limit format. Use a number or "Unlimited"'
                }, status=HTTPStatus.BAD_REQUEST)

        if promotion_type not in ['discount', 'free_trial']:
            return Response({'error': 'Invalid promotion type'}, status=HTTPStatus.BAD_REQUEST)

        # Handle promotion amount based on type
        if promotion_type == 'free_trial':
            promotion_amount = 30  # Default 30 days free trial
        else:  # discount type
            try:
                promotion_amount = int(request.data.get('promotionAmount', 0))
                if promotion_amount < 0 or promotion_amount > 100:
                    return Response({
                        'error': True,
                        'message': 'Discount must be between 0 and 100 percent'
                    }, status=HTTPStatus.BAD_REQUEST)
            except (ValueError, TypeError):
                return Response({
                    'error': True,
                    'message': 'Invalid promotion amount'
                }, status=HTTPStatus.BAD_REQUEST)

        # Create a Promotion in database
        promotion = Promotion.objects.create(
            creator=creator,
            promotion_type=promotion_type,
            promotion_amount=promotion_amount,
            end_date=end_date,
            redemption_limit=redemption_limit
        )
        
        serializer = PromotionSerializer(promotion)
        return Response({
            'message': 'Promotion created successfully',
            'data': serializer.data
        }, status=HTTPStatus.CREATED)
    except Exception as e:
        print(e)
        return Response({
            'error': True,
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_promotion(request, promotion_id):
    try:
        promotion = Promotion.objects.get(pk=promotion_id, creator__user=request.user)
        promotion.delete()
        
        return Response({
            'message': 'Promotion deleted successfully'
        }, status=HTTPStatus.OK)
    except Promotion.DoesNotExist:
        return Response({
            'error': True,
            'message': 'Promotion not found'
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({
            'error': True,
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_subscribed_creators(request):
    spectator = get_object_or_404(Spectator, user=request.user)
    
    # Get all subscriptions
    subscriptions = Subscription.objects.filter(spectator=spectator)
    
    # Process any expired subscriptions
    for subscription in subscriptions:
        check_and_process_subscription(subscription)
    
    # Get updated list of active subscriptions
    subscribed_creators = spectator.subscriptions.all().order_by('user__username')

    paginator = PageNumberPagination()
    paginator.page_size = 10
    page = paginator.paginate_queryset(subscribed_creators, request)

    if page is not None:
        serializer = CreatorSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    
    return Response([], status=HTTPStatus.OK)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_subscribers(request):
    try:
        creator = Creator.objects.get(user=request.user)
        
        # Get search query from request parameters
        search_query = request.GET.get('search', '')
        
        # Get all subscriptions for this creator
        subscribers = Subscription.objects.filter(creator=creator)
        
        # Apply search filter if provided
        if search_query:
            subscribers = subscribers.filter(
                Q(spectator__user__username__icontains=search_query) |
                Q(spectator__user__first_name__icontains=search_query) |
                Q(spectator__user__last_name__icontains=search_query)
            )
        
        # Get the spectators from the subscriptions
        spectators = [sub.spectator for sub in subscribers]
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page = paginator.paginate_queryset(spectators, request)

        print(page)
        if page is not None:
            # Pass the creator to the serializer context
            context = {'request': request, 'creator': creator}
            serializer = SpectatorSerializer(page, many=True, context=context)
            return paginator.get_paginated_response(serializer.data)
        
        return Response([], status=HTTPStatus.OK)
        
    except Creator.DoesNotExist:
        return Response(
            {'error': True, 'message': 'creator_not_found'},
            status=HTTPStatus.NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': True, 'message': str(e)},
            status=HTTPStatus.INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_promotions(request, creator_id):
    """
    Get all active promotions for a specific creator.
    """
    try:
        creator = get_object_or_404(Creator, pk=creator_id)
        
        # Get all active promotions that haven't expired
        promotions = Promotion.objects.filter(
            creator=creator,
            is_active=True
        ).exclude(
            end_date__lt=timezone.now()
        ).order_by('-created_at')

        # Filter out promotions that have reached their redemption limit
        valid_promotions = [
            promo for promo in promotions 
            if not (promo.redemption_limit and promo.redemption_count >= promo.redemption_limit)
        ]
        
        serializer = PromotionSerializer(valid_promotions, many=True)

        print(serializer.data)
        
        return Response({
            'message': 'Successfully retrieved promotions',
            'data': serializer.data
        }, status=HTTPStatus.OK)
        
    except Creator.DoesNotExist:
        return Response({
            'error': True,
            'message': 'Creator not found'
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({
            'error': True,
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)