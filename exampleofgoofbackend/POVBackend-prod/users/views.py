# users/views.py
import asyncio
import os
import threading
from venv import logger
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from http import HTTPStatus
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from analytics.tasks import create_daily_snapshots
from common import models
from payments.models import Tip
from users.notifications import send_fcm_notification
from videos.models import Vision
from videos.serializers import VisionSerializer
from .models import CollabInvite, EmailVerificationRequest, Report, SignInCodeRequest, User, Interest, Creator, Badge, UserBadge, WatchHistory, SupportRequest
from .serializers import BadgeSerializer, UserBadgeSerializer, InterestSerializer, CreatorSerializer, UserSerializer
import cloudinary.uploader
from django.db.models import Sum, F, ExpressionWrapper, FloatField, Q
from django.db.models.functions import Coalesce
from rest_framework.authentication import TokenAuthentication
from rest_framework import status
from django.contrib.postgres.search import TrigramSimilarity
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.db.models import Avg, Count, Q
from django.core.cache import cache
from subscriptions.models import Promotion, Subscription
import stripe
from django.conf import settings
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)
from datetime import datetime, timedelta
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed
from analytics.services import AnalyticsService
from .models import UserActivity, NotificationTemplate
from django.utils import translation
from .activity_manager import ActivityManager
from events.models import Event
from django.contrib.auth.hashers import check_password, make_password
import boto3
import pyotp
from users.models import Spectator
import random
from firebase_admin import messaging
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_profile_picture(request):
    try:
        if 'profile_picture' not in request.FILES:
            return Response({'error': True, 'message': 'No file uploaded'}, status=HTTPStatus.BAD_REQUEST)

        user = request.user  # Get the authenticated user
        profile_picture = request.FILES['profile_picture']
        print(f"Received file: {profile_picture.name}")
        
        # Proceed with the upload
        res = cloudinary.uploader.upload(
            profile_picture, 
            public_id=f'profile_picture_{user.username}', 
            overwrite=True, 
            unique_filename=True
        )
        
        # Update the profile picture URL
        user.profile_picture_url = res['secure_url']
        print(res['secure_url'])
        user.save()  # Save the user instance to the database
        print(user.profile_picture_url)
        return Response({'message': 'Profile picture updated successfully', 'profile_picture': user.profile_picture_url})
    except Exception as e:
        print(f"Error: {str(e)}")
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_profile_picture_username(request):
    try:
        user = User.objects.get(pk=request.user.pk)  # Fetch user from database using pk
        
        # Check if profile picture is provided
        if 'profile_picture' in request.FILES:
            profile_picture = request.FILES['profile_picture']
            print(f"Received file: {profile_picture.name}")
            
            # Proceed with the upload
            res = cloudinary.uploader.upload(
                profile_picture, 
                public_id=f'profile_picture_{user.username}', 
                overwrite=True, 
                unique_filename=True
            )
            
            # Update the profile picture URL
            user.profile_picture_url = res['secure_url']
            print(res['secure_url'])
        
        # Check if username is provided
        if 'username' in request.data:
            new_username = request.data['username']

            # Check if the username is already taken
            if User.objects.filter(username=new_username).exclude(id=user.id).exists():
                print("Username is already taken")
                return Response({"error": "This username is already taken."}, status=status.HTTP_400_BAD_REQUEST)
            
            user.username = new_username
            
        # Handle date of birth
        if 'date_of_birth' in request.data and request.data['date_of_birth']:
            try:
                user.birth_date = timezone.datetime.fromisoformat(request.data['date_of_birth'].replace('Z', '+00:00')).date()
            except ValueError:
                print("Invalid date format for date_of_birth")
                return Response({"error": "Invalid date format for date_of_birth"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Handle gender
        if 'gender' in request.data and request.data['gender']:
            gender = request.data['gender']
            if gender not in ['M', 'F', 'O']:
                print("Invalid gender value. Must be 'M', 'F', or 'O'")
                return Response({"error": "Invalid gender value. Must be 'M', 'F', or 'O'"}, status=status.HTTP_400_BAD_REQUEST)
            user.gender = gender
        
        user.save()  # Save the user instance to the database
        
        return Response({
            'message': 'Profile updated successfully',
            'profile_picture': user.profile_picture_url,
            'username': user.username,
            'birth_date': user.birth_date.isoformat() if user.birth_date else None,
            'gender': user.gender
        })
    except Exception as e:
        print(f"Error: {str(e)}")
        return Response({'error': True, 'message': 'There was an error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_user_details(request):
    user = User.objects.get(pk=request.user.pk)
    
    # Get the data from the request
    username = request.data.get('username')
    bio = request.data.get('bio')
    profile_picture = request.FILES.get('profile_picture')
    profile_banner = request.FILES.get('profile_banner')

    # Update the fields if they are provided
    if username:
        # Check if the username is already taken
        if User.objects.filter(username=username).exclude(id=user.id).exists():
            print("Username is already taken")
            return Response({"error": "This username is already taken."}, status=status.HTTP_400_BAD_REQUEST)
        user.username = username

    if bio:
        user.creator.bio = bio

    if profile_picture:
        res = cloudinary.uploader.upload(
            profile_picture, 
            public_id=f'profile_picture_{user.username}', 
            overwrite=True, 
            unique_filename=True
        )
        user.profile_picture_url = res['secure_url']

    if profile_banner:
        res = cloudinary.uploader.upload(
            profile_banner, 
            public_id=f'profile_banner_{user.username}', 
            overwrite=True, 
            unique_filename=True
        )
        user.cover_picture_url = res['secure_url']

    try:
        user.save()
        if bio:
            user.creator.save()
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"Error: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([AllowAny])
def interest(request):
    try:
        paginator = PageNumberPagination()
        paginator.page_size = 20
        interests = Interest.objects.annotate(vision_count=Count('vision')).order_by('-vision_count')
        results = paginator.paginate_queryset(interests, request)

        logger.info(f"Interests: {interests}")
        
        return Response({
            'data': InterestSerializer(results, many=True).data,
            'size': len(interests),
            'next': paginator.get_next_link(),
            'prev': paginator.get_previous_link()
        })
    except Exception as e:
        logger.exception(f"Error in interest view: {e}")
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    try:
        user = User.objects.get(pk=request.user.pk)  # Fetch the user from database by checking pk
        serializer = UserSerializer(user)  # Serialize the user data
        print(serializer.data)  # Debugging line
        return Response(serializer.data)  # Return the serialized data
    except User.DoesNotExist:
        return Response({'error': True, 'message': 'User not found'}, status=404)
    except Exception as e:
        return Response({'error': True, 'message': str(e)}, status=500)


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_interests(request):
    try:
        user = User.objects.get(pk=request.user.pk)
        spectator = user.spectator
        interests = spectator.interests.all()
        serialized_interests = InterestSerializer(interests, many=True).data
        logger.info(f"Serialized interests: {serialized_interests}")
        return Response({'interests': serialized_interests}, status=200)
    except Exception as e:
        return Response({'error': True, 'message': str(e)}, status=500)
    
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_or_remove_interest_from_spectator(request):
    try:
        add_interests = request.data.get('add_interests', [])
        remove_interests = request.data.get('remove_interests', [])

        if not add_interests and not remove_interests:
            return Response({
                'error': True, 
                'message': 'No interests provided to add or remove'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get fresh user instance from database
        user = User.objects.get(pk=request.user.pk)
        spectator = getattr(user, 'spectator', None)
        
        # Create spectator profile if it doesn't exist
        if not spectator:
            spectator = Spectator.objects.create(user=user)

        # Remove specified interests
        for interest_name in remove_interests:
            try:
                interest = Interest.objects.get(name=interest_name)
                spectator.interests.remove(interest)
            except Interest.DoesNotExist:
                continue  # Skip non-existent interests

        # Add specified interests
        for interest_name in add_interests:
            try:
                interest = Interest.objects.get(name=interest_name)
                spectator.interests.add(interest)
            except Interest.DoesNotExist:
                continue  # Skip non-existent interests

        # Get updated interests for response
        updated_interests = InterestSerializer(spectator.interests.all(), many=True).data

        return Response({
            'message': 'Interests updated successfully!',
            'interests': updated_interests
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error in add_or_remove_interest_from_spectator: {str(e)}")
        return Response({
            'error': True,
            'message': 'An error occurred while updating interests'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def search_interests(request):
    try:
        query = request.data.get('search_text', '')

        if not query:
            logger.error("No search query provided")
            return Response({
                'message': 'Please provide a search query',
                'error': True
            }, status=status.HTTP_400_BAD_REQUEST)

        interests = Interest.objects.annotate(
            similarity=TrigramSimilarity('name', query)
        ).filter(similarity__gt=0.2).order_by('-similarity')

        return Response({
            'message': 'Interests found',
            'data': InterestSerializer(interests, many=True).data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        print(e)
        return Response({'message': str(e), 'error': True}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_or_create_interests(request):
    try:
        interests = request.data.get('interests', [])
        
        if not interests:
            return Response({'error': True, 'message': 'No interests provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        interest_objects = []
        for interest_name in interests:
            interest, created = Interest.objects.get_or_create(name=interest_name)
            interest_objects.append({
                'id': interest.id,
                'name': interest.name,
                'created': created
            })

        return Response({
            'interests': interest_objects
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': True, 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_popular_creators(request):
    try:
        interest = request.GET.get('interest')

        # Start with base query
        popular_creators = Creator.objects.annotate(
            total_views=Coalesce(Sum('vision__views'), 0),
            total_likes=Coalesce(Sum('vision__likes'), 0),
            weighted_score=ExpressionWrapper(
                (F('total_views') * 1) +  
                (F('total_likes') * 3) +  
                (F('subscriber_count') * 5),  
                output_field=FloatField()
            )
        )

        # Filter by interest if provided
        if interest:
            try:
                interest_obj = Interest.objects.get(name=interest)
                popular_creators = popular_creators.filter(
                    vision__interests=interest_obj
                ).distinct()
            except Interest.DoesNotExist:
                return Response({'error': 'Interest not found'}, status=status.HTTP_404_NOT_FOUND)

        popular_creators = popular_creators.order_by('-weighted_score')

        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(popular_creators, request)
        
        serializer = CreatorSerializer(results, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def creator_live_status(request, creator_id):
    try:
        creator = Creator.objects.get(pk=creator_id)
        
        # Get the creator's live vision (assuming only one can be live at a time)
        live_vision = Vision.objects.filter(creator=creator, live=True).first()
        
        status_data = {
            'is_live': live_vision is not None,
            'creator_id': creator_id,
            'vision': VisionSerializer(live_vision, context={'request': request}).data if live_vision else None
        }
        
        return Response(status_data)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_creators(request):
    try:
        search_text = request.data.get('search_text', '')
        interest_name = request.data.get('interest')

        logger.error(f"Request data: {request.data}")
        logger.error(f"Search text: {search_text}")
        logger.error(f"Interest name: {interest_name}")

        # Base queryset
        creators = Creator.objects.all()

        if search_text:
            # Use trigram similarity for partial matches
            creators = creators.annotate(
                username_similarity=TrigramSimilarity('user__username', search_text),
                bio_similarity=TrigramSimilarity('bio', search_text)
            ).filter(
                Q(username_similarity__gt=0.1) |
                Q(bio_similarity__gt=0.1) |
                Q(user__username__icontains=search_text) |  # Direct contains match
                Q(bio__icontains=search_text)  # Direct contains match
            ).order_by('-username_similarity', '-bio_similarity')

        # Apply interest filter if provided
        if interest_name:
            try:
                interest = Interest.objects.get(name=interest_name)
                creators = creators.filter(user__spectator__interests=interest)
            except Interest.DoesNotExist:
                return Response({'error': 'Interest not found'}, status=status.HTTP_404_NOT_FOUND)

        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10  # Set the number of items per page
        result_page = paginator.paginate_queryset(creators, request)

        serializer = CreatorSerializer(result_page, many=True)

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error in search_creators: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_badges(request):
    badges = Badge.objects.all()
    serializer = BadgeSerializer(badges, many=True, context={'request': request})
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_badges(request):
    user_badges = UserBadge.objects.filter(user=request.user)
    serializer = UserBadgeSerializer(user_badges, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_username_availability(request):
    try:
        username = request.data.get('username')
        if not username:
            return Response({'error': 'Username is required'}, status=status.HTTP_400_BAD_REQUEST)

        is_available = not User.objects.filter(username=username).exists()
        return Response({'available': is_available})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_analytics_overview(request):
    """Get high-level analytics metrics"""
    try:
        creator = Creator.objects.select_related('user').get(user=request.user)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator account not found'}, status=status.HTTP_404_NOT_FOUND)
    
    time_span = request.query_params.get('time_span', '30')
    if not time_span.isdigit():
        return Response({'error': 'Invalid time span'}, status=status.HTTP_400_BAD_REQUEST)
    
    analytics_service = AnalyticsService(creator, int(time_span))
    
    try:
        latest_data = analytics_service.get_latest_analytics_data()
        demographics = analytics_service.get_demographics_data()
        
        overview_data = {
            'time_span': f'{time_span} days',
            **latest_data,
            **demographics
        }

        logger.info(f"Overview data: {overview_data}")
        
        return Response(overview_data)
    except Exception as e:
        logger.error(f"Error fetching analytics overview: {str(e)}")
        return Response(
            {'error': 'An error occurred while fetching analytics overview'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_analytics_detailed(request):
    """Get detailed daily financial metrics"""
    try:
        creator = Creator.objects.select_related('user').get(user=request.user)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator account not found'}, status=status.HTTP_404_NOT_FOUND)
    
    time_span = request.query_params.get('time_span', '30')
    if not time_span.isdigit():
        return Response({'error': 'Invalid time span'}, status=status.HTTP_400_BAD_REQUEST)
    
    analytics_service = AnalyticsService(creator, int(time_span))
    
    try:
        detailed_data = analytics_service.get_detailed_analytics_data_points()

        logger.info(f"Detailed data: {detailed_data}")
        return Response({'detailed_daily_points': detailed_data})
    except Exception as e:
        logger.error(f"Error fetching detailed analytics: {str(e)}")
        return Response(
            {'error': 'An error occurred while fetching detailed analytics'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_analytics_audience(request):
    """Get audience engagement metrics"""
    try:
        creator = Creator.objects.select_related('user').get(user=request.user)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator account not found'}, status=status.HTTP_404_NOT_FOUND)
    
    time_span = request.query_params.get('time_span', '30')
    if not time_span.isdigit():
        return Response({'error': 'Invalid time span'}, status=status.HTTP_400_BAD_REQUEST)
    
    analytics_service = AnalyticsService(creator, int(time_span))
    
    try:
        audience_data = analytics_service.get_audience_analytics_data_points()
        
        logger.info(f"Audience data: {audience_data}")
        
        return Response({'audience_daily_points': audience_data})
    except Exception as e:
        logger.error(f"Error fetching audience analytics: {str(e)}")
        return Response(
            {'error': 'An error occurred while fetching audience analytics'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_collab_invites(request):
    try:
        user = request.user
        creator = Creator.objects.get(user=user)
        
        # Get all future collab invites for this creator
        now = timezone.now()
        invites = CollabInvite.objects.filter(
            (Q(host_creator=creator) | Q(invited_creators=creator)) &
            (Q(event__start_time__gt=now) | Q(vision__created_at__gt=now))
        ).distinct()
        
        invites_data = []
        for invite in invites:
            invite_data = {
                'id': invite.id,
                'host_creator': invite.host_creator.user.username,
                'invited_creators': [c.user.username for c in invite.invited_creators.all()],
                'event': invite.event.id if invite.event else None,
                'vision': invite.vision.id if invite.vision else None,
                'status': invite.status,
                'created_at': invite.created_at,
                'updated_at': invite.updated_at
            }
            invites_data.append(invite_data)
        
        return Response(invites_data)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def accept_collab_invite(request, invite_id):
    try:
        user = request.user
        creator = Creator.objects.get(user=user)
        invite = CollabInvite.objects.get(id=invite_id, invited_creators=creator)
        
        if invite.status != 'PENDING':
            return Response({'error': 'This invite is no longer pending'}, status=status.HTTP_400_BAD_REQUEST)
        
        invite.status = 'ACCEPTED'
        invite.save()
        
        # Create activity and notify the host creator
        ActivityManager.create_activity_and_notify(
            actor=user,
            action_type='accept_collab',
            target_id=invite.id,
            target_type='collab_invite',
            notify_user=invite.host_creator.user,
            notification_title="Collab Invite Accepted",
            notification_body=f"{user.username} accepted your collab invite"
        )
        
        return Response({'message': 'Collaboration invite accepted successfully'})
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except CollabInvite.DoesNotExist:
        return Response({'error': 'Invite not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def decline_collab_invite(request, invite_id):
    try:
        user = request.user
        creator = Creator.objects.get(user=user)
        invite = CollabInvite.objects.get(id=invite_id, invited_creators=creator)
        
        if invite.status != 'PENDING':
            return Response({'error': 'This invite is no longer pending'}, status=status.HTTP_400_BAD_REQUEST)
        
        invite.status = 'DECLINED'
        invite.save()
        
        # Create activity and notify the host creator
        ActivityManager.create_activity_and_notify(
            actor=user,
            action_type='decline_collab',
            target_id=invite.id,
            target_type='collab_invite',
            notify_user=invite.host_creator.user,
            notification_title="Collab Invite Declined",
            notification_body=f"{user.username} declined your collab invite"
        )
        
        return Response({'message': 'Collaboration invite declined successfully'})
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except CollabInvite.DoesNotExist:
        return Response({'error': 'Invite not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_active_promotions(request):
    try:
        user = request.user
        creator = Creator.objects.get(user=user)
        
        # Get all active promotions for this creator
        active_promotions = Promotion.objects.filter(creator=creator, is_active=True)
        
        promotions_data = []
        for promotion in active_promotions:
            promotion_data = {
                'pk': promotion.pk,
                'promotion_type': promotion.promotion_type,
                'promotion_amount': promotion.promotion_amount,
                'end_date': promotion.end_date,
                'redemption_limit': promotion.redemption_limit,
                'redemption_count': promotion.redemption_count,
                'is_active': promotion.is_active,
                'created_at': promotion.created_at
            }
            promotions_data.append(promotion_data)
        
        return Response(promotions_data)
    except Creator.DoesNotExist:
        print("Creator not found")
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def cancel_promotion(request, promotion_id):
    try:
        user = request.user
        creator = Creator.objects.get(user=user)
        promotion = Promotion.objects.get(id=promotion_id, creator=creator)

        if not promotion.is_active:
            return Response({'error': 'This promotion is already inactive'}, status=status.HTTP_400_BAD_REQUEST)

        # Deactivate the promotion
        promotion.is_active = False
        promotion.save()

        return Response({'message': 'Promotion cancelled successfully'})
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=status.HTTP_404_NOT_FOUND)
    except Promotion.DoesNotExist:
        return Response({'error': 'Promotion not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_user_notifications(request):
    user = request.user
    language = request.GET.get('language', 'en')
    translation.activate(language)

    notifications = UserActivity.objects.filter(user=user).order_by('-created_at')[:20]  # Get last 20 notifications
    
    notification_data = []
    for notification in notifications:
        event = notification.event
        creator = Creator.objects.get(user=event.actor)
        
        activity_item = {
            'pk': notification.pk,
            'creator': {
                'pk': creator.pk,
                'user': {
                    'profile_picture_url': creator.user.profile_picture_url,
                    'username': creator.user.username,
                    'bio': creator.bio,
                    'is_verified': creator.is_verified,
                },
                'subscription_price': str(creator.subscription_price),
                'subscriber_count': creator.subscriber_count,
            },
            'text': f"{event.actor.username} {event.action_type}d your {event.target_type}",
            'created_at': event.timestamp.isoformat(),
            'image_url': None,  # You may want to add an image_url field to your ActivityEvent model if needed
        }
        
        notification_data.append(activity_item)
    
    return Response(notification_data, status=status.HTTP_200_OK)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_invite(request):
    try:
        creator_id = request.data.get('creator_id')
        vision_id = request.data.get('vision_id')
        user = request.user

        try:
            creator = Creator.objects.get(pk=creator_id)
        except Creator.DoesNotExist:
            return Response({"message": "Creator not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            vision = Vision.objects.get(pk=vision_id)
        except Vision.DoesNotExist:
            return Response({"message": "Vision not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if invite already exists
        if CollabInvite.objects.filter(host_creator__user=user, invited_creators=creator, status='PENDING', vision=vision).exists():
            return Response({"message": "Invite already sent"}, status=status.HTTP_400_BAD_REQUEST)

        # Create the invite
        invite = CollabInvite.objects.create(host_creator=user.creator, vision=vision)
        invite.invited_creators.add(creator)
        invite.save()

        # Create activity and notify the invited creator
        ActivityManager.create_activity_and_notify(
            actor=user,
            action_type='send_collab_invite',
            target_id=invite.id,
            target_type='collab_invite',
            notify_user=creator.user,
            notification_title="New Collab Invite",
            notification_body=f"{user.username} invited you to collaborate on a vision"
        )

        return Response({'message': 'Collaboration invite sent successfully'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def cancel_invite(request):
    try:
        creator_id = request.data.get('creator_id')
        user = request.user

        try:
            creator = Creator.objects.get(pk=creator_id)
        except Creator.DoesNotExist:
            return Response({"message": "Creator not found"}, status=status.HTTP_404_NOT_FOUND)

        invite = CollabInvite.objects.filter(
            host_creator__user=user,
            invited_creators=creator,
            status='PENDING'
        ).first()

        if not invite:
            return Response({'error': 'Invite not found or already processed'}, status=status.HTTP_404_NOT_FOUND)

        # Delete the invite
        invite.delete()

        # Notify the invited creator
        ActivityManager.create_activity_and_notify(
            actor=user,
            action_type='cancel_collab_invite',
            target_id=creator_id,
            target_type='collab_invite',
            notify_user=creator.user,
            notification_title="Collab Invite Cancelled",
            notification_body=f"{user.username} cancelled the collab invite"
        )

        return Response({'message': 'Collaboration invite cancelled successfully'})
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def remove_activity(request):
    try:
        activity_id = request.data.get('activity_id')
        if not activity_id:
            return Response({'error': 'activity_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        activity = UserActivity.objects.get(id=activity_id, user=request.user)
        activity.delete()
        return Response({'message': 'Activity removed successfully'}, status=status.HTTP_200_OK)
    except UserActivity.DoesNotExist:
        return Response({'error': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_blocked_users(request):
    try:
        user = User.objects.get(pk=request.user.pk)
        blocked_users = user.blocked_users.all()
        serializer = UserSerializer(blocked_users, many=True)
        return Response(serializer.data)
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def block_user(request):
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        user_to_block = User.objects.get(pk=user_id)
        current_user = User.objects.get(pk=request.user.pk)
        
        # Add user to blocked users
        current_user.blocked_users.add(user_to_block)
        current_user.save()
        
        # If current user is a creator, remove blocked user from subscribers
        try:
            creator = Creator.objects.get(user=current_user)
            try:
                spectator = Spectator.objects.get(user=user_to_block)
                
                # Check if the blocked user is subscribed to the creator
                subscription = Subscription.objects.filter(
                    spectator=spectator, 
                    creator=creator
                ).first()
                
                if subscription:
                    # For paid subscriptions, set end date and deactivate
                    if subscription.subscription_type == 'paid':
                        subscription.end_date = subscription.next_payment_date or timezone.now()
                        subscription.next_payment_date = None
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
            except Spectator.DoesNotExist:
                pass
        except Creator.DoesNotExist:
            pass
        
        return Response({'message': 'User blocked successfully'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def unblock_user(request):
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        user_to_unblock = User.objects.get(pk=user_id)
        current_user = User.objects.get(pk=request.user.pk)
        
        # Remove user from blocked users
        current_user.blocked_users.remove(user_to_unblock)
        current_user.save()
        
        return Response({'message': 'User unblocked successfully'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        print(e)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def change_password(request):
    try:
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response({
                'success': False,
                'message': 'Both current and new passwords are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # Check if the current password is correct
        if not check_password(current_password, user.password):
            return Response({
                'success': False,
                'message': 'Current password is incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set the new password
        user.password = make_password(new_password)
        user.save()

        return Response({
            'success': True,
            'message': 'Password changed successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def initiate_two_factor_auth(request):
    try:
        phone_number = request.data.get('phone_number')
        if not phone_number:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the phone number is already in use
        if User.objects.filter(phone_number=phone_number).exclude(id=request.user.id).exists():
            return Response({'error': 'This phone number is already in use'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate a secret key for TOTP
        secret = pyotp.random_base32()

        # Generate a TOTP code
        totp = pyotp.TOTP(secret, digits=5)
        code = totp.now()

        # Send SMS using AWS SNS
        client = boto3.client(
            "sns",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION,
        )

        client.publish(
            PhoneNumber=phone_number,
            Message=f"Your verification code is: {code}"
        )

        # Save the secret and phone number to the user model
        request.user.two_factor_secret = secret
        request.user.phone_number = phone_number
        request.user.save()

        return Response({'message': 'Verification code sent successfully'}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def verify_two_factor_auth(request):
    try:
        code = request.data.get('code')
        if not code:
            return Response({'error': 'Verification code is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify the TOTP code
        totp = pyotp.TOTP(request.user.two_factor_secret)
        if totp.verify(code):
            request.user.two_factor_enabled = True
            request.user.save()
            return Response({'message': 'Two-factor authentication enabled successfully'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid verification code'}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def disable_two_factor_auth(request):
    try:
        request.user.two_factor_enabled = False
        request.user.two_factor_secret = None
        request.user.save()
        return Response({'message': 'Two-factor authentication disabled successfully'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_watch_history(request):
    try:
        watch_history = WatchHistory.objects.filter(user=request.user).order_by('-watched_at')
        visions = [entry.vision for entry in watch_history]
        serializer = VisionSerializer(visions, many=True, context={'request': request})
        return Response(serializer.data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def remove_from_watch_history(request, vision_id):
    try:
        WatchHistory.objects.filter(user=request.user, vision_id=vision_id).delete()
        return Response({'message': 'Vision removed from watch history'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def clear_watch_history(request):
    try:
        WatchHistory.objects.filter(user=request.user).delete()
        return Response({'message': 'Watch history cleared'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_to_watch_history(request):
    vision_id = request.data.get('vision_id')
    try:
        vision = Vision.objects.get(pk=vision_id)
        
        WatchHistory.objects.create(user=request.user, vision=vision)

        return Response({'message': 'Added to watch history'}, status=status.HTTP_200_OK)
    except Vision.DoesNotExist:
        return Response({'error': 'Vision not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_support_request(request):
    try:
        issue_type = request.data.get('issue_type')
        additional_info = request.data.get('additional_info')

        if not issue_type or not additional_info:
            return Response({
                'success': False,
                'message': 'Both issue_type and additional_info are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save the support request to the database
        user = User.objects.get(pk=request.user.pk)
        
        support_request = SupportRequest.objects.create(
            user=user,
            issue_type=issue_type,
            additional_info=additional_info
        )

        # Create SES client
        ses_client = boto3.client(
            'ses',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION
        )

        # Prepare email content
        subject = f"Support Request: {issue_type}"
        html_content = f"""
        <strong>Support Request from {request.user.username}</strong><br>
        <p><strong>Issue Type:</strong> {issue_type}</p>
        <p><strong>Additional Information:</strong> {additional_info}</p>
        """
        text_content = f"""
        Support Request from {request.user.username}
        Issue Type: {issue_type}
        Additional Information: {additional_info}
        """

        try:
            response = ses_client.send_email(
                Source=settings.SUPPORT_EMAIL,  # Make sure to add this to your settings
                Destination={
                    'ToAddresses': [settings.SUPPORT_EMAIL]
                },
                Message={
                    'Subject': {
                        'Data': subject
                    },
                    'Body': {
                        'Text': {
                            'Data': text_content
                        },
                        'Html': {
                            'Data': html_content
                        }
                    }
                }
            )

            return Response({
                'success': True,
                'message': 'Support request sent successfully',
                'request_id': support_request.id
            }, status=status.HTTP_200_OK)

        except ses_client.exceptions.MessageRejected:
            # If email fails, still keep the request in the database
            return Response({
                'success': True,
                'message': 'Support request recorded, but email notification failed',
                'request_id': support_request.id
            }, status=status.HTTP_200_OK)
        except Exception as e:
            # Log the error but don't expose it to the user
            print(f"Error sending support request email: {str(e)}")
            return Response({
                'success': True,
                'message': 'Support request recorded, but email notification failed',
                'request_id': support_request.id
            }, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error sending support request: {str(e)}")
        return Response({
            'success': False,
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def update_profile_picture_url(request):
    try:
        username = request.data.get('username')
        profile_picture_url = request.data.get('profile_picture_url')

        if not username or not profile_picture_url:
            return Response({
                'error': 'Both username and profile_picture_url are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user and update profile picture URL
        user = User.objects.get(username=username)
        user.profile_picture_url = profile_picture_url
        user.save()

        return Response({
            'message': 'Profile picture URL updated successfully',
            'username': username,
            'profile_picture_url': profile_picture_url
        })
    except User.DoesNotExist:
        return Response({
            'error': 'User not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_fcm_token(request):
    """
    Update the FCM token for the authenticated user.
    
    Args:
        request (Request): The incoming HTTP request containing the FCM token.
        
    Returns:
        Response:
            - 200 OK if token was updated successfully
            - 400 BAD REQUEST if token is missing
            - 500 INTERNAL SERVER ERROR for unexpected errors
    """
    try:
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            return Response({'error': 'FCM token is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Get user model instance
        user = User.objects.get(id=request.user.id)
        user.fcm_token = fcm_token
        user.save(update_fields=['fcm_token'])

        return Response({'message': 'FCM token updated successfully'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating FCM token: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_notification(request):
    """
    Send a notification to a single user.
    
    Required POST data:
    - user_id: ID of the user to send notification to
    - title: Notification title
    - body: Notification body
    - data: Optional dictionary of additional data
    """
    try:
        user_id = request.data.get('user_id')
        title = request.data.get('title')
        body = request.data.get('body')
        data = request.data.get('data', {})

        if not all([user_id, title, body]):
            return Response({
                'error': 'user_id, title, and body are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)

        from .notifications import send_fcm_notification
        success = send_fcm_notification(target_user, title, body, data)

        if success:
            return Response({
                'message': 'Notification sent successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to send notification'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_bulk_notification(request):
    """
    Send a notification to multiple users.
    
    Required POST data:
    - user_ids: List of user IDs to send notification to
    - title: Notification title
    - body: Notification body
    - data: Optional dictionary of additional data
    """
    try:
        user_ids = request.data.get('user_ids', [])
        title = request.data.get('title')
        body = request.data.get('body')
        data = request.data.get('data', {})

        if not all([user_ids, title, body]) or not isinstance(user_ids, list):
            return Response({
                'error': 'user_ids (as list), title, and body are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        users = User.objects.filter(id__in=user_ids)
        if not users.exists():
            return Response({
                'error': 'No valid users found'
            }, status=status.HTTP_404_NOT_FOUND)

        from .notifications import send_fcm_notification_to_multiple_users
        success_count, failure_count = send_fcm_notification_to_multiple_users(users, title, body, data)

        return Response({
            'message': 'Bulk notification process completed',
            'success_count': success_count,
            'failure_count': failure_count
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error sending bulk notification: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def report(request):
    """
    Create a report for a chat message, comment, or vision.
    
    Required POST data:
    - type: Type of report ('chat', 'comment', 'vision')
    - reported_user_id: ID of the user being reported
    - reason: Optional reason for the report
    - vision_id: Required if type is 'vision'
    - chat_message: Required if type is 'chat'
    - comment_id: Required if type is 'comment'
    """
    try:
        report_type = request.data.get('type')
        reported_user_id = request.data.get('reported_user_id')
        reason = request.data.get('reason')

        if not report_type or not reported_user_id:
            return Response({
                'error': 'type and reported_user_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if report_type not in ['chat', 'comment', 'vision']:
            return Response({
                'error': 'Invalid report type'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            reported_user = User.objects.get(pk=reported_user_id)
        except User.DoesNotExist:
            return Response({
                'error': 'Reported user not found'
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            reporter = User.objects.get(pk=request.user.pk)
        except User.DoesNotExist:
            return Response({
                'error': 'Reporter not found'
            }, status=status.HTTP_404_NOT_FOUND)

        report_data = {
            'reporter': reporter,
            'reported_user': reported_user,
            'type': report_type,
            'reason': reason
        }

        # Add the specific content based on report type
        content_details = ""
        if report_type == 'vision':
            vision_id = request.data.get('vision_id')
            if not vision_id:
                return Response({
                    'error': 'vision_id is required for vision reports'
                }, status=status.HTTP_400_BAD_REQUEST)
            try:
                vision = Vision.objects.get(pk=vision_id)
                report_data['vision'] = vision
                content_details = f"Vision ID: {vision_id}\nVision Title: {vision.title}"
            except Vision.DoesNotExist:
                return Response({
                    'error': 'Vision not found'
                }, status=status.HTTP_404_NOT_FOUND)

        elif report_type == 'chat':
            chat_message = request.data.get('chat_message')
            if not chat_message:
                return Response({
                    'error': 'chat_message is required for chat reports'
                }, status=status.HTTP_400_BAD_REQUEST)
            report_data['chat_message'] = chat_message
            content_details = f"Chat Message: {chat_message}"

        elif report_type == 'comment':
            comment_id = request.data.get('comment_id')
            if not comment_id:
                return Response({
                    'error': 'comment_id is required for comment reports'
                }, status=status.HTTP_400_BAD_REQUEST)
            try:
                from videos.models import Comment
                comment = Comment.objects.get(pk=comment_id)
                report_data['comment'] = comment
                content_details = f"Comment ID: {comment_id}\nComment Text: {comment.text}"
            except Comment.DoesNotExist:
                return Response({
                    'error': 'Comment not found'
                }, status=status.HTTP_404_NOT_FOUND)

        report = Report.objects.create(**report_data)

        # Send email notification to admin
        try:
            # Create SES client
            ses_client = boto3.client(
                'ses',
                aws_access_key_id=settings.AWS_ACCESS_KEY,
                aws_secret_access_key=settings.AWS_SECRET_KEY,
                region_name=settings.AWS_REGION
            )

            # Prepare email content
            subject = f"New {report_type.title()} Report"
            html_content = f"""
            <h2>New Report Submitted</h2>
            <p><strong>Report ID:</strong> {report.id}</p>
            <p><strong>Report Type:</strong> {report_type}</p>
            <p><strong>Reporter:</strong> {reporter.username} (ID: {reporter.id})</p>
            <p><strong>Reported User:</strong> {reported_user.username} (ID: {reported_user.id})</p>
            <p><strong>Reason:</strong> {reason or 'No reason provided'}</p>
            <p><strong>Content Details:</strong><br>{content_details}</p>
            <p><strong>Time:</strong> {report.created_at}</p>
            """
            text_content = f"""
            New Report Submitted
            Report ID: {report.id}
            Report Type: {report_type}
            Reporter: {reporter.username} (ID: {reporter.id})
            Reported User: {reported_user.username} (ID: {reported_user.id})
            Reason: {reason or 'No reason provided'}
            Content Details:
            {content_details}
            Time: {report.created_at}
            """

            ses_client.send_email(
                Source=settings.DEFAULT_FROM_EMAIL,
                Destination={
                    'ToAddresses': [settings.ADMIN_EMAIL]  # Make sure to add this to your settings
                },
                Message={
                    'Subject': {
                        'Data': subject
                    },
                    'Body': {
                        'Text': {
                            'Data': text_content
                        },
                        'Html': {
                            'Data': html_content
                        }
                    }
                }
            )
        except Exception as e:
            # Log the error but don't fail the report creation
            logger.error(f"Failed to send report notification email: {str(e)}")

        return Response({
            'message': 'success',
            'report_id': report.id
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Error creating report: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
     
async def trigger_analytics_async():
    """Async function to create daily analytics snapshots"""
    try:
        from asgiref.sync import sync_to_async
        from analytics.tasks import create_daily_snapshots
        await sync_to_async(create_daily_snapshots)()
        logger.info("Analytics snapshots created successfully")
    except Exception as e:
        logger.error(f"Error in analytics async task: {str(e)}")

@api_view(['POST'])
@permission_classes([AllowAny])
def trigger_analytics(request):
    """
    Endpoint to trigger daily analytics snapshot and compute event similarities.
    This endpoint should only be called by AWS Lambda with proper authentication.
    Triggers background tasks and returns response immediately.
    """
    try:
        # Verify the request is from our Lambda function
        auth_token = request.headers.get('X-Analytics-Auth-Token')
        if not auth_token or auth_token != os.environ.get('ANALYTICS_AUTH_TOKEN'):
            return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

        def run_background_tasks():
            try:
                # Create and set event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Define coroutine for all tasks
                async def process_tasks():
                    try:
                        # Trigger analytics snapshots
                        await trigger_analytics_async()
                        
                        # Run similarity computations in executor
                        from events.management.commands.compute_event_similarities import Command as ComputeEventSimilarities
                        from videos.management.commands.compute_similarities import Command as ComputeVisionSimilarities
                        
                        loop.run_in_executor(None, ComputeEventSimilarities().handle)
                        logger.info("Successfully computed event similarities")
                        
                        loop.run_in_executor(None, ComputeVisionSimilarities().handle)
                        logger.info("Successfully computed vision similarities")
                    except Exception as e:
                        logger.error(f"Error in process_tasks: {str(e)}")

                # Run the tasks
                try:
                    loop.run_until_complete(process_tasks())
                except Exception as e:
                    logger.error(f"Error running tasks: {str(e)}")
                finally:
                    try:
                        # Clean up any remaining tasks
                        pending = asyncio.all_tasks(loop)
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        
                        # Close the loop
                        loop.run_until_complete(loop.shutdown_asyncgens())
                        loop.stop()
                        loop.close()
                    except Exception as e:
                        logger.error(f"Error cleaning up loop: {str(e)}")

            except Exception as e:
                logger.error(f"Error in run_background_tasks: {str(e)}")

        # Start background thread
        thread = threading.Thread(target=run_background_tasks, daemon=True)
        thread.start()

        return Response({'message': 'Analytics snapshot and similarities computation triggered successfully'})
    except Exception as e:
        logger.error(f"Error triggering analytics: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def initiate_email_verification(request):
    """
    Initiate email verification process by sending a verification code via AWS SES.
    """
    try:
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Check if this is a forgot password request
        is_forgot_password = request.data.get('is_forgot_password', False)
        if is_forgot_password:
            if not User.objects.filter(email=email).exists():
                return Response({'error': 'No account found with this email'}, status=status.HTTP_404_NOT_FOUND)

        # Check if the email is already in use
        if User.objects.filter(email=email).exists() and not is_forgot_password:
            return Response({'error': 'This email is already in use'}, status=status.HTTP_400_BAD_REQUEST)

        # Delete any existing pending verification requests for this email
        EmailVerificationRequest.objects.filter(
            email=email,
            status='pending'
        ).delete()

        # Generate a verification code
        verification_code = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        print('verification_code', verification_code)

        # Create SES client
        ses_client = boto3.client(
            'ses',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION
        )

        # Set expiry time (minutes)
        expiry_minutes = 15
        
        # Get user name if available (for forgot password)
        user_name = "there"
        if is_forgot_password:
            try:
                user = User.objects.get(email=email)
                if user.first_name:
                    user_name = user.first_name
            except User.DoesNotExist:
                pass

        # Render the HTML template with context
        from django.template.loader import render_to_string
        email_context = {
            'verification_code': verification_code,
            'user_name': user_name,
            'expiry_minutes': expiry_minutes
        }
        email_subject = 'Your Verification Code'
        email_body_html = render_to_string('email/verification_code.html', email_context)
        email_body_text = f'Your verification code is: {verification_code}. This code will expire in {expiry_minutes} minutes.'

        try:
            response = ses_client.send_email(
                Source=settings.DEFAULT_FROM_EMAIL,
                Destination={
                    'ToAddresses': [email]
                },
                Message={
                    'Subject': {
                        'Data': email_subject
                    },
                    'Body': {
                        'Text': {
                            'Data': email_body_text
                        },
                        'Html': {
                            'Data': email_body_html
                        }
                    }
                }
            )

            # Create a verification request
            verification_request = EmailVerificationRequest.objects.create(
                email=email,
                code=verification_code,
                status='pending'
            )

            return Response({
                'message': 'Verification code sent successfully',
                'request_id': verification_request.id
            }, status=status.HTTP_200_OK)

        except ses_client.exceptions.MessageRejected:
            return Response({
                'error': 'Email address is not verified in AWS SES'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error sending verification code: {str(e)}")
            return Response({
                'error': 'Failed to send verification code'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        print(f"Error sending verification code: {str(e)}")
        return Response({
            'error': 'Failed to send verification code'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    """
    Verify email using the verification code sent via AWS SES.
    """
    try:
        code = request.data.get('code')
        email = request.data.get('email')
        request_id = request.data.get('request_id')

        if not all([code, email, request_id]):
            return Response({
                'error': 'Code, email, and request_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            verification_request = EmailVerificationRequest.objects.get(
                id=request_id,
                email=email,
                code=code,
                status='pending'
            )
        except EmailVerificationRequest.DoesNotExist:
            return Response({
                'error': 'Invalid or expired verification code'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if code is not expired (15 minutes)
        if timezone.now() > verification_request.created_at + timedelta(minutes=15):
            verification_request.delete()
            return Response({
                'error': 'Verification code has expired'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update verification request status
        verification_request.status = 'success'
        verification_request.save()

        return Response({
            'message': 'Email verified successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error verifying email: {str(e)}")
        return Response({
            'error': 'Failed to verify email'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification_code(request):
    """
    Resend email verification code using AWS SES.
    """
    try:
        email = request.data.get('email')
        if not email:
            return Response({
                'error': 'Email is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Delete expired verification requests
        EmailVerificationRequest.objects.filter(
            created_at__lt=timezone.now() - timedelta(minutes=15)
        ).delete()

        # Delete any existing pending verification requests for this email
        EmailVerificationRequest.objects.filter(
            email=email,
            status='pending'
        ).delete()

        # Generate a new verification code
        verification_code = ''.join([str(random.randint(0, 9)) for _ in range(5)])
        print('resend verification_code', verification_code)

        # Create SES client
        ses_client = boto3.client(
            'ses',
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION
        )

        # Create email content
        email_subject = 'Email Verification Code'
        email_body_html = f'<p>Your new email verification code is: <strong>{verification_code}</strong></p>'
        email_body_text = f'Your new email verification code is: {verification_code}'

        try:
            response = ses_client.send_email(
                Source=settings.DEFAULT_FROM_EMAIL,
                Destination={
                    'ToAddresses': [email]
                },
                Message={
                    'Subject': {
                        'Data': email_subject
                    },
                    'Body': {
                        'Text': {
                            'Data': email_body_text
                        },
                        'Html': {
                            'Data': email_body_html
                        }
                    }
                }
            )

            # Create a new verification request
            verification_request = EmailVerificationRequest.objects.create(
                email=email,
                code=verification_code,
                status='pending'
            )

            return Response({
                'message': 'Verification code resent successfully',
                'request_id': verification_request.id
            }, status=status.HTTP_200_OK)

        except ses_client.exceptions.MessageRejected:
            return Response({
                'error': 'Email address is not verified in AWS SES'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error resending verification code: {str(e)}")
            return Response({
                'error': 'Failed to resend verification code'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        print(f"Error resending verification code: {str(e)}")
        return Response({
            'error': 'Failed to resend verification code'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_confirm(request):
    """
    Reset user's password after email verification.
    Requires email and new password.
    """
    try:
        email = request.data.get('email')
        new_password = request.data.get('new_password')

        if not email or not new_password:
            return Response({
                'error': 'Email and new password are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({
                'error': 'No account found with this email'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if there's a successful email verification
        verification = EmailVerificationRequest.objects.filter(
            email=email,
            status='success'
        ).order_by('-created_at').first()

        if not verification:
            return Response({
                'error': 'Email not verified'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if verification is not too old (e.g., within last 30 minutes)
        if timezone.now() > verification.created_at + timedelta(minutes=30):
            return Response({
                'error': 'Email verification has expired. Please verify your email again.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update password
        user.password = make_password(new_password)
        user.save()

        # Delete the verification request
        verification.delete()

        return Response({
            'message': 'Password reset successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"Error resetting password: {str(e)}")
        return Response({
            'error': 'Failed to reset password'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_user_country(request):
    """
    Update the user's country name.
    
    Required POST data:
    - country_name: Full country name
    """
    try:
        country_name = request.data.get('country_name')

        if not country_name:
            return Response({
                'error': 'country_name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user and update country information
        user = User.objects.get(pk=request.user.pk)
        user.country = country_name
        user.save()

        return Response({
            'message': 'Country information updated successfully',
            'country_name': country_name
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({
            'error': 'User not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error updating user country: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def ban_user(request):
    """
    Ban a user with optional temporary duration.
    
    Required POST data:
    - user_id: ID of the user to ban
    - reason: Reason for the ban
    Optional:
    - duration_days: Number of days for temporary ban (if not provided, permanent ban)
    """
    try:
        # Check if the requesting user is an admin
        # if not request.user.is_staff:
        #     return Response({
        #         'error': 'Only administrators can ban users'
        #     }, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user_id')
        reason = request.data.get('reason')
        duration_days = request.data.get('duration_days')

        if not user_id or not reason:
            return Response({
                'error': 'user_id and reason are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_ban = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Don't allow banning of other admin users
        if user_to_ban.is_staff:
            return Response({
                'error': 'Cannot ban administrative users'
            }, status=status.HTTP_403_FORBIDDEN)

        user_to_ban.is_banned = True
        user_to_ban.ban_reason = reason
        user_to_ban.banned_at = timezone.now()

        if duration_days:
            try:
                duration_days = int(duration_days)
                user_to_ban.banned_until = timezone.now() + timedelta(days=duration_days)
            except ValueError:
                return Response({
                    'error': 'duration_days must be a valid number'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            user_to_ban.banned_until = None  # Permanent ban

        user_to_ban.save()

        # Send notification to banned user
        try:
            from .notifications import send_fcm_notification
            send_fcm_notification(
                user_to_ban,
                "Account Banned",
                f"Your account has been banned. Reason: {reason}"
            )
        except Exception as e:
            logger.error(f"Failed to send ban notification: {str(e)}")

        return Response({
            'message': 'User banned successfully',
            'ban_details': {
                'user_id': user_to_ban.id,
                'reason': reason,
                'banned_at': user_to_ban.banned_at,
                'banned_until': user_to_ban.banned_until
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error banning user: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def unban_user(request):
    """
    Unban a previously banned user.
    
    Required POST data:
    - user_id: ID of the user to unban
    """
    try:
        # Check if the requesting user is an admin
        # if not request.user.is_staff:
        #     return Response({
        #         'error': 'Only administrators can unban users'
        #     }, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'error': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_unban = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({
                'error': 'User not found'
            }, status=status.HTTP_404_NOT_FOUND)

        if not user_to_unban.is_banned:
            return Response({
                'error': 'User is not banned'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Clear ban-related fields
        user_to_unban.is_banned = False
        user_to_unban.ban_reason = None
        user_to_unban.banned_at = None
        user_to_unban.banned_until = None
        user_to_unban.save()

        # Send notification to unbanned user
        try:
            from .notifications import send_fcm_notification
            send_fcm_notification(
                user_to_unban,
                "Account Unbanned",
                "Your account has been unbanned. You can now use the platform again."
            )
        except Exception as e:
            logger.error(f"Failed to send unban notification: {str(e)}")

        return Response({
            'message': 'User unbanned successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error unbanning user: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def check_ban_status(request):
    """
    Check if the authenticated user is banned.
    
    Returns:
    - is_banned: boolean indicating if user is banned
    - ban_details: details about the ban if user is banned
    """
    try:
        # Get fresh user instance from database
        user = User.objects.get(pk=request.user.pk)

        # Check if user is banned and if temporary ban has expired
        is_banned = user.is_banned
        if is_banned and user.banned_until:
            if timezone.now() >= user.banned_until:
                # Ban has expired, automatically unban the user
                user.is_banned = False
                user.ban_reason = None
                user.banned_at = None
                user.banned_until = None
                user.save()
                
                is_banned = False

        response_data = {
            'is_banned': is_banned
        }

        if is_banned:
            response_data['ban_details'] = {
                'reason': user.ban_reason,
                'banned_at': user.banned_at,
                'banned_until': user.banned_until,
                'is_permanent': user.banned_until is None
            }

        return Response(response_data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response({
            'error': True,
            'message': 'User not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error checking ban status: {str(e)}")
        return Response({
            'error': True,
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_notification_settings(request):
    """Update user's notification settings"""
    try:
        user = User.objects.get(pk=request.user.pk)
        
        # Update notification settings if provided
        if 'notify_subscriptions' in request.data:
            user.notify_subscriptions = request.data['notify_subscriptions']
        if 'notify_recommended_visions' in request.data:
            user.notify_recommended_visions = request.data['notify_recommended_visions']
        if 'notify_comment_replies' in request.data:
            user.notify_comment_replies = request.data['notify_comment_replies']
        if 'notify_vision_activity' in request.data:
            user.notify_vision_activity = request.data['notify_vision_activity']
            
        user.save()
        
        return Response({
            'message': 'Successfully updated notification settings',
            'settings': {
                'notify_subscriptions': user.notify_subscriptions,
                'notify_recommended_visions': user.notify_recommended_visions,
                'notify_comment_replies': user.notify_comment_replies,
                'notify_vision_activity': user.notify_vision_activity
            }
        }, status=HTTPStatus.OK)
    except Exception as e:
        logger.error(f"Error updating notification settings: {str(e)}")
        return Response({
            'message': 'Error updating notification settings',
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_notification_settings(request):
    """Get user's notification settings"""
    try:
        user = User.objects.get(pk=request.user.pk)
        
        return Response({
            'settings': {
                'notify_subscriptions': user.notify_subscriptions,
                'notify_recommended_visions': user.notify_recommended_visions,
                'notify_comment_replies': user.notify_comment_replies,
                'notify_vision_activity': user.notify_vision_activity
            }
        }, status=HTTPStatus.OK)
    except Exception as e:
        logger.error(f"Error fetching notification settings: {str(e)}")
        return Response({
            'message': 'Error fetching notification settings',
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_notification_by_token(request):
    """
    Send a notification directly using an FCM token.
    
    Required POST data:
    - fcm_token: Firebase Cloud Messaging token
    - title: Notification title
    - body: Notification body
    Optional:
    - data: Additional data to send with the notification (dict)
    """
    try:
        fcm_token = request.data.get('fcm_token')
        title = request.data.get('title')
        body = request.data.get('body')
        data = request.data.get('data', {})

        if not all([fcm_token, title, body]):
            return Response({
                'error': 'fcm_token, title, and body are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user by FCM token
        try:
            user = User.objects.get(fcm_token=fcm_token)
        except User.DoesNotExist:
            return Response({
                'error': 'No user found with this FCM token'
            }, status=status.HTTP_404_NOT_FOUND)

        # Use the notification helper function
        success = send_fcm_notification(user, title, body, data)

        if success:
            return Response({
                'message': 'Notification sent successfully'
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to send notification'
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f"Error in send_notification_by_token: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def toggle_creator_reminder(request):
    """
    Toggle a creator in the user's reminder list.
    
    Required POST data:
    - creator_id: ID of the creator to toggle reminder for
    """
    try:
        creator_id = request.data.get('creator_id')
        if not creator_id:
            return Response({
                'error': 'creator_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            creator = Creator.objects.get(pk=creator_id)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=status.HTTP_404_NOT_FOUND)

        spectator = Spectator.objects.get(user=request.user)

        # Toggle the creator in reminder_creators
        if creator in spectator.reminder_creators.all():
            spectator.reminder_creators.remove(creator)
            is_reminded = False
        else:
            spectator.reminder_creators.add(creator)
            is_reminded = True

        return Response({
            'success': True,
            'message': 'Creator reminder toggled successfully',
            'is_reminded': is_reminded
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error toggling creator reminder: {str(e)}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
