import logging
import re
import cloudinary.uploader
import boto3
from botocore.client import Config
from django.forms import DurationField
from payments.models import CreditBalance, CreditTransaction
from rest_framework.response import Response
from django.db.models.functions import ExtractDay, Random, Coalesce, Extract, Cast, Greatest
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from http import HTTPStatus
from django.db.models import (
    Count, Q, F, ExpressionWrapper, FloatField, Case, 
    When, Value, IntegerField, Subquery, OuterRef, Exists
)
from users.notifications import send_fcm_notification, send_fcm_notification_to_multiple_users
from .models import Invite, StoryNode, StoryOption, Vision, Comment, VisionRequest, VisionSimilarity
from .serializers import CommentSerializer, InviteSerializer, VisionSerializer
from users.models import Interest, Spectator, Creator, User
import os
from django.utils import timezone
from datetime import timedelta
from rest_framework.authentication import TokenAuthentication
from django.conf import settings
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db import transaction, models
from .models import Vision, Poll, PollItem, Vote
from users.models import Spectator, WatchHistory, ViewCount
from .serializers import PollSerializer, PollItemSerializer
from firebase_admin import firestore, credentials
import json
from django.core.paginator import Paginator
from users.activity_manager import ActivityManager
from botocore.exceptions import ClientError
import b2sdk.v2 as b2
from io import BytesIO
import random
from django.core.cache import cache
from django.utils.http import quote_etag
from django.views.decorators.http import etag
from annoy import AnnoyIndex
import tempfile

logger = logging.getLogger(__name__)

import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

# Add this constant at the top of the file if not already there
CACHE_PREFIX = "vision_similarity_"
CACHE_TIMEOUT = 60 * 60  # 1 hour

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_vision(request):
    try:
        # Get interests string from request and split into list
        interests_str = request.data.get('interests', '')
        interests = [interest.strip() for interest in interests_str.split(',') if interest.strip()]

        # Convert interests to list of Interest models
        interest_models = []
        for interest_name in interests:
            interest, created = Interest.objects.get_or_create(name=interest_name)
            interest_models.append(interest.pk)

        vision_data = request.data.copy()
        vision_data['interests'] = interest_models

        vision_request_id = request.data.get('vision_request_id')
        vision_request = None
        if vision_request_id:
            try:
                vision_request = VisionRequest.objects.get(pk=vision_request_id)
                if vision_request.creator.user.pk != request.user.pk:
                    return Response({'error': 'You do not have permission to create vision for this request'},
                                    status=HTTPStatus.FORBIDDEN)
                if vision_request.status != 'accepted':
                    return Response({'error': 'Can only create vision for accepted requests'},
                                    status=status.HTTP_400_BAD_REQUEST)
            except VisionRequest.DoesNotExist:
                return Response({'error': 'Vision request not found'},
                                status=HTTPStatus.NOT_FOUND)
        
        user = User.objects.get(pk=request.user.pk)
        
        vision_instance = Vision.objects.create(
            title=vision_data['title'],
            description=vision_data['description'],
            aspect_ratio=vision_data.get('aspect_ratio', '16:9'),
            stereo_mapping=vision_data.get('stereo_mapping', 'normal'),
            is_interactive=str(vision_data.get('is_interactive', 'false')).lower() == 'true',
            is_highlight=str(vision_data.get('is_highlight', 'false')).lower() == 'true',
            views=vision_data.get('views', 0),
            status='draft',
            creator=Creator.objects.get(user=user),
            access_type=vision_data.get('access_type', 'free'),
            ppv_price=vision_data.get('price_credits', 0),
            private_user=vision_request.requester if vision_request else None,
            vision_request=vision_request
        )
        vision_instance.interests.set(vision_data['interests'])

        thumbnail = request.FILES.get('thumbnail')
        if thumbnail:
            thumbnail_res = cloudinary.uploader.upload(
                thumbnail,
                public_id=f'{request.user.username}-{vision_instance.pk}-thumbnail',
                unique_filename=False,
                overwrite=True
            )
            vision_instance.thumbnail = thumbnail_res['secure_url']
            vision_instance.save()

        # Initialize Backblaze B2 client
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account("production", os.environ.get("B2_KEY_ID"), os.environ.get("B2_APPLICATION_KEY"))
        b2_bucket = b2_api.get_bucket_by_name(os.environ.get("B2_BUCKET_NAME"))
        
        filename = f'{request.user.username}-{vision_instance.title.replace(" ", "")}-vision-{vision_instance.pk}.mp4'

        vision_instance.status = 'pending_upload'
        vision_instance.save()

        # Get upload URL and authorization token
        upload_auth = b2_api.session.get_upload_url(b2_bucket.get_id())
        upload_url = upload_auth['uploadUrl'] 
        upload_auth_token = upload_auth['authorizationToken']

        # Set the file URL in B2
        file_url = f"b2://{os.environ.get('B2_BUCKET_NAME')}/{filename}"
        vision_instance.url = file_url
        vision_instance.save()

        # Generate download URL
        download_url = f"https://{os.environ.get('B2_DOWNLOAD_URL')}/file/{os.environ.get('B2_BUCKET_NAME')}/{filename}"

        return Response({
            'id': vision_instance.pk,
            'get_url': download_url,
            'b2data': {
                'uploadUrl': upload_url,
                'authorizationToken': upload_auth_token,
                'fileName': filename,
                'bucketName': os.environ.get('B2_BUCKET_NAME'),
                'contentType': 'video/mp4'
            }
        })
    except Exception as e:
        logger.error(f"Error creating vision: {e}")
        return Response({'error': True, 'message': 'There was an error'},
                        status=HTTPStatus.BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_live_vision(request):
    try:
        # Get vision_obj based on client request
        title = request.data.get('title')
        description = request.data.get('description')
        interests = request.data.get('interests', '').split(',')
        thumbnail = request.FILES.get('thumbnail')
        access_type = request.data.get('access_type', 'free')
        ppv_price = request.data.get('price_credits')

        # Create new Vision instance directly
        vision_instance = Vision.objects.create(
            title=title,
            description=description,
            creator=Creator.objects.get(pk=request.user.pk),
            live=True,
            access_type=access_type,
            ppv_price=ppv_price if ppv_price else 0
        )

        # Add interests
        for interest_name in interests:
            interest_name = interest_name.strip()
            if interest_name:
                interest, _ = Interest.objects.get_or_create(name=interest_name)
                vision_instance.interests.add(interest)

        # Generate and save RTMP stream info
        stream_key = f'{request.user.username}-{vision_instance.pk}'
        
        vision_instance.rtmp_link = f'rtmp://{settings.RTMP_HOST}:1935/stream/'
        vision_instance.stream_key = stream_key

        # Set the URL for HLS playback
        vision_instance.url = f'{settings.FILE_HOST}/{stream_key}.m3u8'
        vision_instance.status = 'live'
        
        # Get thumbnail upload
        if thumbnail:
            thumbnail_res = cloudinary.uploader.upload(
                thumbnail,
                public_id=f'{request.user.username}-{vision_instance.pk}-thumbnail',
                unique_filename=False,
                overwrite=True
            )
            vision_instance.thumbnail = thumbnail_res['secure_url']
        
        vision_instance.save()

        print('stream_key')
        print(stream_key)
        
        return Response({
            'vision': VisionSerializer(vision_instance, context={'request': request}).data,
            'rtmp_stream_key': stream_key,
        })

    except Exception as e:
        logger.error(f"Error creating live vision: {e}")
        return Response({'error': True, 'message': 'There was an error creating live vision'}, status=HTTPStatus.BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def end_live_vision(request):
    api_key = request.data.get('api_key')
    stream_key = request.data.get('stream_key')

    logger.info(f"Received end_live_vision request for stream_key: {stream_key}")

    if api_key != settings.NGINX_API_KEY:
        logger.warning(f"Unauthorized end_live_vision attempt with invalid API key")
        return Response({"error": "Unauthorized"}, status=401)
    
    try:
        # Parse stream key
        try:
            username, vision_id = stream_key.split('-', 1)
        except ValueError:
            logger.error(f"Invalid stream key format: {stream_key}")
            return Response({'error': True, 'message': 'Invalid stream key format'}, status=HTTPStatus.BAD_REQUEST)

        # Get user and vision
        try:
            user = User.objects.get(username=username)
            vision = Vision.with_locks.with_is_locked(user).get(pk=vision_id)
        except User.DoesNotExist:
            logger.error(f"User not found: {username}")
            return Response({'error': True, 'message': 'User not found'}, status=HTTPStatus.NOT_FOUND)
        except Vision.DoesNotExist:
            logger.error(f"Vision not found: {vision_id}")
            return Response({'error': True, 'message': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)

        if True:
            vision.live = False
            
            # Initialize B2 client
            try:
                info = b2.InMemoryAccountInfo()
                b2_api = b2.B2Api(info)
                b2_api.authorize_account("production", os.environ.get("B2_KEY_ID"), os.environ.get("B2_APPLICATION_KEY"))
                b2_bucket = b2_api.get_bucket_by_name(os.environ.get("B2_BUCKET_NAME"))
                logger.info(f"Successfully initialized B2 client for stream: {stream_key}")
            except Exception as e:
                logger.error(f"Failed to initialize B2 client: {str(e)}")
                raise
            
            # Get master playlist file from B2 bucket
            master_playlist_key = f'{stream_key}.m3u8'
            try:
                file_info = b2_bucket.get_file_info_by_name(master_playlist_key)
                download_buffer = BytesIO()
                b2_bucket.download_file_by_id(file_info.id_).save(download_buffer)
                master_content = download_buffer.getvalue().decode('utf-8')
                logger.info(f"Successfully downloaded master playlist for stream: {stream_key}")
            except Exception as e:
                logger.error(f"Error downloading master playlist: {str(e)}\nKey: {master_playlist_key}")
                raise

            logger.debug(f"Master playlist content:\n{master_content}")
            
            # Parse master playlist to get quality variants
            quality_variants = []
            for line in master_content.split('\n'):
                if line.endswith('/index.m3u8'):
                    quality_variants.append(line.strip())

            if not quality_variants:
                logger.error(f"No quality variants found in master playlist for stream: {stream_key}")
                return Response({
                    'error': True, 
                    'message': 'No quality variants found in master playlist'
                }, status=HTTPStatus.BAD_REQUEST)

            logger.info(f"Found {len(quality_variants)} quality variants: {quality_variants}")

            # Process each quality variant
            successful_variants = 0
            for variant_path in quality_variants:
                # The variant path is already relative to the stream key directory
                variant_key = variant_path
                try:
                    # Download variant playlist
                    file_info = b2_bucket.get_file_info_by_name(variant_key)
                    download_buffer = BytesIO()
                    b2_bucket.download_file_by_id(file_info.id_).save(download_buffer)
                    variant_content = download_buffer.getvalue().decode('utf-8')
                    
                    logger.debug(f"Original variant content for {variant_key}:\n{variant_content}")

                    # Store original content hash for comparison
                    original_hash = hash(variant_content)

                    # Modify variant playlist
                    # Add VOD playlist type if not exists
                    if '#EXT-X-PLAYLIST-TYPE:VOD' not in variant_content:
                        # Add after version tag
                        version_tag = '#EXT-X-VERSION:'
                        version_line_end = variant_content.find('\n', variant_content.find(version_tag)) + 1
                        variant_content = (
                            variant_content[:version_line_end] + 
                            '#EXT-X-PLAYLIST-TYPE:VOD\n' +
                            variant_content[version_line_end:]
                        )
                        logger.info(f"Added VOD playlist type to {variant_key}")

                    # Add independent segments tag if not exists
                    if '#EXT-X-INDEPENDENT-SEGMENTS' not in variant_content:
                        version_line_end = variant_content.find('\n', variant_content.find(version_tag)) + 1
                        variant_content = (
                            variant_content[:version_line_end] + 
                            '#EXT-X-INDEPENDENT-SEGMENTS\n' +
                            variant_content[version_line_end:]
                        )
                        logger.info(f"Added independent segments tag to {variant_key}")

                    # Ensure ENDLIST tag exists
                    if '#EXT-X-ENDLIST' not in variant_content:
                        variant_content = variant_content.rstrip() + '\n#EXT-X-ENDLIST\n'
                        logger.info(f"Added ENDLIST tag to {variant_key}")

                    # Verify content was actually modified
                    new_hash = hash(variant_content)
                    if new_hash == original_hash:
                        logger.warning(f"Content for {variant_key} was not modified!")
                        continue

                    logger.debug(f"Modified variant content for {variant_key}:\n{variant_content}")

                    # Upload modified variant playlist
                    b2_bucket.upload_bytes(
                        data_bytes=variant_content.encode('utf-8'),
                        file_name=variant_key,
                        content_type='application/vnd.apple.mpegurl'
                    )

                    # Verify the upload by downloading and comparing
                    verify_buffer = BytesIO()
                    verify_file_info = b2_bucket.get_file_info_by_name(variant_key)
                    b2_bucket.download_file_by_id(verify_file_info.id_).save(verify_buffer)
                    verify_content = verify_buffer.getvalue().decode('utf-8')
                    
                    if verify_content.strip() != variant_content.strip():
                        logger.error(f"Verification failed for {variant_key} - content mismatch!")
                        raise Exception("Uploaded file verification failed")

                    successful_variants += 1
                    logger.info(f"Successfully processed variant {variant_key}")

                except Exception as e:
                    logger.error(f"Error processing variant playlist {variant_path}: {str(e)}")
                    # Continue with other variants even if one fails
                    continue

            if successful_variants == 0:
                logger.error("Failed to process any quality variants successfully")
                return Response({
                    'error': True,
                    'message': 'Failed to process any quality variants'
                }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

            logger.info(f"Successfully processed {successful_variants} out of {len(quality_variants)} variants")

            vision.status = 'vod'
            vision.save()
            logger.info(f"Updated vision status to VOD for stream: {stream_key}")

            # Send notification to the creator
            try:
                vision_title = vision.title or "Untitled"
                send_fcm_notification(
                    vision.creator.user,
                    "Vision Processing Complete",
                    f"Your vision '{vision_title}' is now ready to view",
                    data={
                        'vision_id': str(vision.id),
                        'status': 'vod'
                    }
                )
                logger.info(f"Sent completion notification to creator for stream: {stream_key}")
            except Exception as e:
                logger.error(f"Failed to send notification to creator: {e}")

            return Response({
                'message': 'Successfully ended live vision',
                'variants_processed': successful_variants,
                'total_variants': len(quality_variants)
            })
        else:
            return Response({'message': 'Vision is not live'}, status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error ending live vision: {str(e)}", exc_info=True)
        return Response({
            'error': True, 
            'message': f'Error ending live vision: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    
@api_view(['POST'])
@permission_classes([AllowAny])
def upload_complete(request):
    try:
        # Extract data from request
        api_key = request.data.get('api_key')
        hls_url = request.data.get('hls_url')
        name = request.data.get('name')
        is_interactive_option = request.data.get('is_interactive_option', False)
        node_pk = request.data.get('node_pk')
        vision_id = request.data.get('vision_id')
        option_pk = request.data.get('option_pk')
        status = request.data.get('status', 'success')  # Get status from request, default to success
        failure_reason = request.data.get('reason', 'Unknown error occurred during processing')  # Get failure reason
        duration = request.data.get('duration')  # Get video duration if available

        # Validate API key
        if api_key != settings.NGINX_API_KEY:
            return Response({'error': 'Invalid API key'}, status=HTTPStatus.FORBIDDEN)

        try:
            # Get vision with creator info and vision request
            vision = Vision.objects.select_related(
                'creator', 
                'creator__user',
                'vision_request'
            ).get(pk=vision_id)
        except Vision.DoesNotExist:
            return Response({'error': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)

        # Check if the upload failed
        if status == 'failed':
            # Set vision status to failed
            vision.status = 'failed'
            vision.save(update_fields=['status'])
            
            # If this was a vision request, update its status
            if vision.vision_request:
                vision.vision_request.status = 'failed'
                vision.vision_request.save()
            
            # Notify the creator about the failure
            try:
                vision_title = vision.title or "Untitled"
                send_fcm_notification(
                    vision.creator.user,
                    "Vision Processing Failed",
                    f"There was an error processing your vision '{vision_title}': {failure_reason}",
                    data={
                        'vision_id': str(vision.id),
                        'status': 'failed',
                        'reason': failure_reason
                    }
                )
                logger.info(f"Sent failure notification to creator for vision {vision_id}: {failure_reason}")
            except Exception as e:
                logger.error(f"Failed to send failure notification to creator: {str(e)}")
            
            return Response({'message': 'Vision status updated to failed'})
        
        # If the upload was successful, proceed with normal processing
        # Prepend FILE_HOST to hls_url
        full_url = settings.FILE_HOST + hls_url

        if is_interactive_option:
            # Update the story graph
            if vision.story_graph and 'nodes' in vision.story_graph:
                # Create a deep copy of the story graph
                updated_story_graph = {
                    'nodes': [
                        {
                            'id': node.get('id'),
                            'video_url': node.get('video_url'),
                            'is_local_video': node.get('is_local_video'),
                            'question': node.get('question'),
                            'options': [
                                {
                                    'id': opt.get('id'),
                                    'text': opt.get('text'),
                                    'next_node': opt.get('next_node')
                                }
                                for opt in node.get('options', [])
                            ]
                        }
                        for node in vision.story_graph['nodes']
                    ]
                }
                
                # Find and update the specific node and option
                for node in updated_story_graph['nodes']:
                    if str(node.get('id')) == str(node_pk):
                        node['video_url'] = full_url
                        node['is_local_video'] = False
                        break
                
                # Save the updated story graph
                vision.story_graph = updated_story_graph
                vision.save(update_fields=['story_graph'])

                # Check if all nodes have been processed
                all_processed = True
                for node in updated_story_graph['nodes']:
                    if node.get('is_local_video', True):
                        all_processed = False
                        break
                    if not all_processed:
                        break

                # If everything is processed, update vision status and send notifications
                if all_processed:
                    vision.status = 'vod'
                    vision.save(update_fields=['status'])

                    # If this is a vision request, update its status
                    if vision.vision_request and vision.vision_request.status != 'completed':
                        vision.vision_request.status = 'completed'
                        vision.vision_request.save()

                    # Notify creator
                    try:
                        vision_title = vision.title or "Untitled"
                        send_fcm_notification(
                            vision.creator.user,
                            "Vision Processing Complete",
                            f"Your vision '{vision_title}' is now ready to view",
                            data={
                                'vision_id': str(vision.id),
                                'status': 'vod'
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to send notification to creator: {e}")

                    # Notify users who have reminders set for this creator using batch notification
                    try:
                        reminder_users = User.objects.filter(
                            spectator__reminder_creators=vision.creator
                        ).exclude(id=vision.creator.user.id)  # Exclude creator from reminder notifications

                        if reminder_users.exists():
                            vision_title = vision.title or "Untitled"
                            success_count, failure_count = send_fcm_notification_to_multiple_users(
                                reminder_users,
                                f"New Vision from {vision.creator.user.username}",
                                f"{vision.creator.user.username} has posted a new vision: {vision_title}",
                                data={
                                    'vision_id': str(vision.id),
                                    'creator_id': str(vision.creator.id),
                                    'type': 'new_vision'
                                }
                            )
                            logger.info(f"Batch notification results - Success: {success_count}, Failed: {failure_count}")
                    except Exception as e:
                        logger.error(f"Failed to send batch notifications to reminder users: {e}")

            else:
                return Response({'error': 'Story graph not found'}, status=HTTPStatus.NOT_FOUND)
        else:
            vision.url = full_url
            vision.status = 'vod'
            
            # Save duration if available
            if duration is not None:
                vision.duration = float(duration)
                
            vision.save()

            # If this is a vision request, update its status
            if vision.vision_request and vision.vision_request.status != 'completed':
                vision.vision_request.status = 'completed'
                vision.vision_request.save()

            # Notify creator
            try:
                vision_title = vision.title or "Untitled"
                send_fcm_notification(
                    vision.creator.user,
                    "Vision Processing Complete",
                    f"Your vision '{vision_title}' is now ready to view",
                    data={
                        'vision_id': str(vision.id),
                        'status': 'vod'
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send notification to creator: {e}")

            # Notify users who have reminders set for this creator using batch notification
            try:
                reminder_users = User.objects.filter(
                    spectator__reminder_creators=vision.creator
                ).exclude(id=vision.creator.user.id)  # Exclude creator from reminder notifications

                if reminder_users.exists():
                    vision_title = vision.title or "Untitled"
                    success_count, failure_count = send_fcm_notification_to_multiple_users(
                        reminder_users,
                        f"New Vision from {vision.creator.user.username}",
                        f"{vision.creator.user.username} has posted a new vision: {vision_title}",
                        data={
                            'vision_id': str(vision.id),
                            'creator_id': str(vision.creator.id),
                            'type': 'new_vision'
                        }
                    )
                    logger.info(f"Batch notification results - Success: {success_count}, Failed: {failure_count}")
            except Exception as e:
                logger.error(f"Failed to send batch notifications to reminder users: {e}")

        return Response({'message': 'Upload completed successfully'})

    except Exception as e:
        logger.error(f"Error in upload_complete: {e}")
        
        # Try to set the vision status to failed if we have the vision_id
        try:
            if 'vision_id' in request.data:
                vision_id = request.data.get('vision_id')
                vision = Vision.objects.select_related('creator', 'creator__user').get(pk=vision_id)
                vision.status = 'failed'
                vision.save(update_fields=['status'])
                
                # If this was a vision request, update its status
                if hasattr(vision, 'vision_request') and vision.vision_request:
                    vision.vision_request.status = 'accepted'
                    vision.vision_request.save()
                
                # Notify the creator about the failure
                error_message = str(e)
                try:
                    vision_title = vision.title or "Untitled"
                    send_fcm_notification(
                        vision.creator.user,
                        "Vision Processing Failed",
                        f"There was an error processing your vision '{vision_title}': {error_message}",
                        data={
                            'vision_id': str(vision.id),
                            'status': 'failed',
                            'reason': error_message
                        }
                    )
                except Exception as notification_err:
                    logger.error(f"Failed to send failure notification to creator: {str(notification_err)}")
        except Exception as inner_e:
            logger.error(f"Error handling vision failure in exception handler: {str(inner_e)}")
            
        return Response({
            'error': f'Error processing upload completion: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def upload_thumbnail(request, vision_pk):
    try:
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_pk)
        thumbnail = request.FILES['thumbnail']
        thumbnail_res = cloudinary.uploader.upload(thumbnail, public_id=f'{request.user.username}-{vision.pk}-thumbnail', unique_filename=False, overwrite=True)
        vision.thumbnail = thumbnail_res['secure_url']
        vision.save()
        return Response({'message': 'Successfully uploaded thumbnail'})
    except Exception as e:
        logger.error(f"Error uploading thumbnail: {e}")
        return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_or_get_vision_info(request, vision_pk):
    if request.method == 'GET':
        try:
            vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_pk)
            return Response({'message': 'Successfully retrieved vision', 'data': VisionSerializer(vision, context={'request': request}).data})
        except Vision.DoesNotExist:
            return Response({'error': True, 'message': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.error(f"Error retrieving vision info: {e}")
            return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.BAD_REQUEST)
    elif request.method == 'PUT':
        try:
            vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_pk)

            # Check if thumbnail is included in the request
            if 'thumbnail' in request.FILES:
                thumbnail = request.FILES['thumbnail']
                thumbnail_res = cloudinary.uploader.upload(thumbnail, public_id=f'{request.user.username}-{vision.pk}-thumbnail', unique_filename=False, overwrite=True)
                vision.thumbnail = thumbnail_res['secure_url']

            new_info = VisionSerializer(vision, data=request.data, partial=True, context={'request': request})
            
            if new_info.is_valid():
                new_info.save()
                return Response({'message': 'Successfully updated vision', 'data': new_info.data})
            else:
                return Response({'message': 'There was an error', 'error': new_info.errors}, status=HTTPStatus.BAD_REQUEST)
        except Vision.DoesNotExist:
            return Response({'error': True, 'message': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating vision info: {e}")
            return Response({'error': True, 'message': 'There was an error'}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_recommended_visions(request):
    try:
        page = request.GET.get('page', 1)
        interest = request.GET.get('interest')
        highlights_only = request.GET.get('highlights', '').lower() == 'true'

        # Use both a caching for IDs and for full serialized responses
        cache_key_serialized = f"recommended_visions_serialized_{request.user.pk}_{interest}_{highlights_only}_{page}"
        serialized_response = cache.get(cache_key_serialized)
        
        if serialized_response:
            return Response(serialized_response)

        # Recommendations
        recommended_visions = get_recommended_visions_algorithm(
            request.user, interest=interest, highlights_only=highlights_only
        )
        
        # Efficient pagination
        paginator = PageNumberPagination()
        paginator.page_size = 5
        results = paginator.paginate_queryset(recommended_visions, request)

        # Use serializer only with needed fields
        serializer = VisionSerializer(
            results, 
            many=True, 
            context={'request': request}
        )
        
        response_data = paginator.get_paginated_response(serializer.data).data
        
        # Cache serialized response
        cache.set(cache_key_serialized, response_data, 50)  # Cache for 50 seconds
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Error fetching recommended visions: {e}")
        
        return Response({
            'error': True,
            'message': f'Failed to fetch recommended visions: {str(e)}'
        }, status=HTTPStatus.BAD_REQUEST)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_visions_by_creator(request, pk):
    try:
        creator = Creator.objects.get(pk=pk)
        # If the requesting user is the creator, show all visions regardless of status
        is_creator_visions = request.GET.get('is_creator_visions') == 'true'
        if (request.user.is_authenticated and request.user.pk == pk) and is_creator_visions:
            visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator).order_by('-created_at')
        else:
            # For other users, only show published visions (vod or live)
            visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator, status__in=['vod', 'live']).order_by('-created_at')
        paginator = PageNumberPagination()
        paginator.page_size = 5
        results = paginator.paginate_queryset(visions, request)
        return paginator.get_paginated_response(VisionSerializer(results, many=True, context={'request': request}).data)
    except Creator.DoesNotExist:
        logger.error(f"Creator with pk={pk} not found")
        return Response({'error': 'Creator not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching visions by creator: {e}")
        return Response({'error': True}, status=HTTPStatus.BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_visions_by_interest(request):
    try:
        interests = [Interest.objects.get(name=interest_name) for interest_name in request.data['interests']]
        visions = Vision.with_locks.with_is_locked(request.user).filter(interests__in=interests).filter(~Q(url=None)).filter(status__in=['vod', 'live']).distinct().order_by('-created_at', '-likes')
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)
        return paginator.get_paginated_response(VisionSerializer(results, many=True, context={'request': request}).data)
    except Exception as e:
        logger.error(f"Error fetching visions by interest: {e}")
        return Response({'error': True}, status=HTTPStatus.BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def like_or_unlike_vision(request, pk):
    try:
        # Fetch vision with lock status for the authenticated user
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=pk)
        spectator = Spectator.objects.get(user=request.user)
        
        # Check if the vision is already disliked, if so remove the dislike first
        if vision in spectator.disliked_visions.all():
            vision.dislikes = max(vision.dislikes - 1, 0)
            spectator.disliked_visions.remove(vision)
        
        if vision in spectator.liked_visions.all():
            # Unlike the vision
            vision.likes = max(vision.likes - 1, 0)
            spectator.liked_visions.remove(vision)
            message = 'Vision unliked'
        else:
            # Like the vision
            vision.likes += 1
            spectator.liked_visions.add(vision)
            message = 'Vision liked'
            
            # Get user from database
            user = User.objects.get(pk=request.user.pk)
            
            # Send notification to vision creator
            ActivityManager.create_activity_and_notify(
                actor=user,
                action_type='like',
                target_id=vision.id,
                target_type='vision',
                notify_user=vision.creator.user,
                notification_title="New Like",
                notification_body=f"{request.user.username} liked your vision"
            )
        
        vision.save()
        spectator.save()
        
        return Response({
            'message': message, 
            'likes': vision.likes,
            'dislikes': vision.dislikes
        }, status=status.HTTP_200_OK)
    
    except Vision.DoesNotExist:
        logger.error(f"Vision with pk={pk} does not exist.")
        return Response({'error': 'Vision not found'}, status=status.HTTP_404_NOT_FOUND)
    
    except Spectator.DoesNotExist:
        logger.error(f"Spectator for user {request.user.username} does not exist.")
        return Response({'error': 'Spectator not found'}, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error liking/unliking vision: {e}")
        return Response({'error': 'An unexpected error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def dislike_or_undislike_vision(request, pk):
    try:
        # Fetch vision with lock status for the authenticated user
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=pk)
        spectator = Spectator.objects.get(user=request.user)
        
        # Check if the vision is already liked, if so remove the like first
        if vision in spectator.liked_visions.all():
            vision.likes = max(vision.likes - 1, 0)
            spectator.liked_visions.remove(vision)
        
        if vision in spectator.disliked_visions.all():
            # Undislike the vision
            vision.dislikes = max(vision.dislikes - 1, 0)
            spectator.disliked_visions.remove(vision)
            message = 'Vision undisliked'
        else:
            # Dislike the vision
            vision.dislikes += 1
            spectator.disliked_visions.add(vision)
            message = 'Vision disliked'
        
        vision.save()
        spectator.save()

        return Response({
            'message': message, 
            'likes': vision.likes,
            'dislikes': vision.dislikes
        }, status=status.HTTP_200_OK)
    
    except Vision.DoesNotExist:
        logger.error(f"Vision with pk={pk} does not exist.")
        return Response({'error': 'Vision not found'}, status=status.HTTP_404_NOT_FOUND)
    
    except Spectator.DoesNotExist:
        logger.error(f"Spectator for user {request.user.username} does not exist.")
        return Response({'error': 'Spectator not found'}, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        logger.error(f"Error disliking/undisliking vision: {e}")
        return Response({'error': 'An unexpected error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_to_watch_history(request):
    vision_id = request.data.get('vision_id')
    try:
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_id)
        
        spectator = Spectator.objects.get(user=request.user)
        spectator.watch_history.add(vision)

        # Optional: Limit history to last x videos
        # if spectator.watch_history.count() > 100000:
        #     oldest = spectator.watch_history.order_by('watch_history__id').first()
        #     spectator.watch_history.remove(oldest)

        return Response({'message': 'Added to watch history'}, status=status.HTTP_200_OK)
    except Vision.DoesNotExist:
        return Response({'error': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_subscription_visions(request):
    spectator = Spectator.objects.get(user=request.user)
    subscribed_visions = Vision.with_locks.with_is_locked(request.user).filter(creator__in=spectator.subscriptions.all(), status__in=['vod', 'live']).order_by('-created_at')
    
    paginator = PageNumberPagination()
    paginator.page_size = 10
    page = paginator.paginate_queryset(subscribed_visions, request)
    
    if page is not None:
        serializer = VisionSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    return Response(None)

def generate_etag_for_trending(request, *args, **kwargs):
    # Create an ETag based on latest update time of trending visions
    latest_update = Vision.objects.filter(
        status='vod'
    ).order_by('-last_recommendation_update').values_list(
        'last_recommendation_update', flat=True
    ).first()
    
    if latest_update:
        etag_content = f"trending-{latest_update.isoformat()}-{request.user.id}"
    else:
        etag_content = f"trending-{timezone.now().isoformat()}-{request.user.id}"
    
    return quote_etag(etag_content)

@etag(generate_etag_for_trending)
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_trending_visions(request):
    try:
        # Get query parameters
        page = request.GET.get('page', 1)
        interest = request.GET.get('interest')

        # Create cache key based on user, page, and interest
        cache_key = f"trending_visions_{page}_{interest}"
        cached_results = cache.get(cache_key)
        
        if cached_results:
            return Response(cached_results)

        # Get visions from the last month
        one_month_ago = timezone.now() - timedelta(days=30)

        # Base queryset
        trending_visions = Vision.with_locks.with_is_locked(request.user).filter(
            created_at__gte=one_month_ago,
            private_user=None,
            status__in=['live', 'vod']  # Ensure only live or vod status visions are included
        )

        # Filter by interest if provided
        if interest:
            try:
                interest_obj = Interest.objects.get(name=interest)
                trending_visions = trending_visions.filter(interests=interest_obj)
            except Interest.DoesNotExist:
                return Response({
                    'error': True,
                    'message': 'Interest not found'
                }, status=HTTPStatus.NOT_FOUND)

        # Directly calculate days_old without using DurationField
        trending_visions = trending_visions.annotate(
            days_old=Greatest(
                Extract(timezone.now() - F('created_at'), 'day'),
                Value(1)
            )
        )

        # Annotate with engagement score and calculate the weighted score
        trending_visions = trending_visions.annotate(
            engagement=F('engagement_score'),
            recency_weight=ExpressionWrapper(
                1 / F('days_old'),
                output_field=FloatField()
            ),
            weighted_score=ExpressionWrapper(
                F('engagement') * F('recency_weight'),
                output_field=FloatField()
            )
        ).order_by('-weighted_score')

        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 5
        results = paginator.paginate_queryset(trending_visions, request)
        
        # Serialize the results
        serialized_data = VisionSerializer(results, many=True, context={'request': request}).data
        response = paginator.get_paginated_response(serialized_data).data
        
        # Cache the response for 5 minutes
        cache.set(cache_key, response, 60 * 5)  # 5 minutes
        
        return Response(response)

    except Exception as e:
        logger.error(f"Error fetching trending visions: {e}")
        return Response({
            'error': True,
            'message': f'Failed to fetch trending visions: {str(e)}'
        }, status=HTTPStatus.BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_visions_by_creator_category(request, pk, category):
    try:
        creator = Creator.objects.get(pk=pk)
        
        if category == 'saved':
            visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator, is_saved=True, status__in=['vod', 'live'], private_user=None)
        elif category == 'highlights':
            visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator, is_highlight=True, status__in=['vod', 'live'], private_user=None)
        elif category == 'forme':
            if request.user.is_authenticated:
                visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator, private_user=request.user, status__in=['vod', 'live'])
            else:
                visions = Vision.with_locks.with_is_locked(request.user).filter(creator=creator, status__in=['vod', 'live'], private_user=None)
        else:
            return Response({'error': 'Invalid category'}, status=HTTPStatus.BAD_REQUEST)
        
        visions = visions.order_by('-created_at')
        
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)
        return paginator.get_paginated_response(VisionSerializer(results, many=True, context={'request': request}).data)
    except Creator.DoesNotExist:
        return Response({'error': 'Creator not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=HTTPStatus.BAD_REQUEST)

def get_recommended_visions_algorithm(user, interest=None, highlights_only=False):
    """
    Simplified hybrid recommendation algorithm with strict content type balancing
    to prevent live content from overwhelming high-engagement VOD content
    """
    try:
        # Disabling cache for now to see immediate results
        cache_key = f"user_recommendations_{user.id}_{interest}_{highlights_only}" 
        cached_results = cache.get(cache_key)
        if cached_results:
            return cached_results

        # Get basic user data
        try:
            spectator = Spectator.objects.filter(user=user).prefetch_related(
                'liked_visions', 'subscriptions'
            ).first()
            
            subscribed_creator_ids = []
            liked_vision_ids = []
            
            if spectator:
                subscribed_creator_ids = list(spectator.subscriptions.values_list('pk', flat=True))
                liked_vision_ids = list(spectator.liked_visions.values_list('pk', flat=True))
        except:
            spectator = None
            subscribed_creator_ids = []
            liked_vision_ids = []
            
        # Get base queryset with is_locked annotation
        base_queryset = Vision.with_locks.with_is_locked(user).filter(
            status__in=['vod', 'live'],
            private_user=None
        ).select_related('creator', 'creator__user')
        
        # Apply filters
        if interest:
            base_queryset = base_queryset.filter(interests__name=interest)

        if highlights_only:
            base_queryset = base_queryset.filter(is_highlight=True)
            
        # Create separate queries for live and VOD content - different scoring for each
        # 1. Live content query - score mostly by recency
        live_visions = base_queryset.filter(status='live').annotate(
            engagement=F('likes') * 10 + F('comment_count') * 5 + F('views') * 0.01,
            subscribed=Case(
                When(creator_id__in=subscribed_creator_ids, then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField()
            ),
            final_score=F('engagement') + Case(
                When(subscribed=True, then=Value(30.0)),
                default=Value(0.0),
                output_field=FloatField()
            )
        ).order_by('-final_score', '-created_at')[:30]
        
        # 2. VOD content query - score by engagement and recency
        vod_visions = base_queryset.filter(status='vod').annotate(
            days_old=Greatest(Extract(timezone.now() - F('created_at'), 'day'), Value(1)),
            engagement=F('likes') * 10 + F('comment_count') * 5 + F('views') * 0.01,
            subscribed=Case(
                When(creator_id__in=subscribed_creator_ids, then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField()
            ),
            recency_component=10.0 / F('days_old'),
            final_score=F('engagement') + F('recency_component') + Case(
                When(subscribed=True, then=Value(30.0)),
                default=Value(0.0),
                output_field=FloatField()
            )
        ).order_by('-final_score')[:60]
        
        # Make lists from querysets
        live_list = list(live_visions)
        vod_list = list(vod_visions)
        
        # Create balanced final list
        final_results = []
        
        # Never have more than 40% live content in top results
        max_live_ratio = 0.4
        
        # Add 1 live, 2 VOD, 1 live, 2 VOD, etc. 
        while (live_list or vod_list) and len(final_results) < 100:
            # Calculate current live ratio
            current_live_count = sum(1 for item in final_results if item.status == 'live')
            
            # If we've hit our live content ratio, only add VOD content
            if current_live_count >= len(final_results) * max_live_ratio and live_list:
                # Only add VOD for a while
                if vod_list:
                    final_results.append(vod_list.pop(0))
                else:
                    # No more VOD, we have to add live
                    final_results.append(live_list.pop(0))
            else:
                # We can add either content type
                # Every 3rd item, add a live item if available
                if len(final_results) % 3 == 0 and live_list:
                    final_results.append(live_list.pop(0))
                elif vod_list:
                    final_results.append(vod_list.pop(0))
                elif live_list:
                    final_results.append(live_list.pop(0))
            
            # Stop if we've used up all content
            if not live_list and not vod_list:
                break
        
        # Cache results
        cache.set(cache_key, final_results, 60 * 5)  # 5 minutes
        return final_results

    except Exception as e:
        logger.error(f"Error in recommendation algorithm: {e}", exc_info=True)
        # Fallback to basic engagement-based trending
        return Vision.with_locks.with_is_locked(user).filter(
            status__in=['vod', 'live']
        ).annotate(
            engagement=F('likes') * 10 + F('comment_count') * 5 + F('views') * 0.01
        ).order_by('-engagement')[:100]

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def like_comment(request, comment_pk):
    try:
        comment = Comment.objects.get(pk=comment_pk)
        user = User.objects.get(pk=request.user.pk)
        
        if user not in comment.likes.all():
            comment.likes.add(user)
            
            # Send notification to comment creator
            ActivityManager.create_activity_and_notify(
                actor=user,
                action_type='like',
                target_id=comment.id,
                target_type='comment',
                notify_user=comment.user,
                notification_title="New Like",
                notification_body=f"{user.username} liked your comment"
            )
            
            return Response({'message': 'Comment liked successfully'}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'Comment already liked'}, status=status.HTTP_200_OK)
    
    except Comment.DoesNotExist:
        return Response({'error': 'Comment not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        print('Error liking comment:', e)
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def unlike_comment(request, comment_pk):
    try:
        comment = Comment.objects.get(pk=comment_pk)
        user = User.objects.get(pk=request.user.pk)
        
        if user in comment.likes.all():
            comment.likes.remove(user)
            return Response({'message': 'Comment unliked successfully'}, status=status.HTTP_200_OK)
        else:
            return Response({'message': 'Comment was not liked'}, status=status.HTTP_200_OK)
    
    except Comment.DoesNotExist:
        print('Comment not found')
        return Response({'error': 'Comment not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        print('Error unliking comment:', e)
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def search_visions(request):
    try:
        search_text = request.data.get('search_text', '')
        interest_name = request.data.get('interest')

        # Create the search vector
        search_vector = SearchVector('title', weight='A') + \
                       SearchVector('description', weight='B') + \
                       SearchVector('interests__name', weight='C') + \
                       SearchVector('creator__user__username', weight='A')  # Add creator username with high weight

        # Create the search query
        search_query = SearchQuery(search_text)

        # Filter and rank the results
        visions = Vision.with_locks.with_is_locked(request.user).annotate(
            rank=SearchRank(search_vector, search_query)
        ).filter(
            Q(rank__gte=0.01) |
            Q(creator__user__username__icontains=search_text)  # Direct username match
        ).filter(status__in=['vod', 'live']).order_by('-rank')

        # Apply interest filter if provided
        if interest_name:
            try:
                interest = Interest.objects.get(name=interest_name)
                visions = visions.filter(interests=interest)
            except Interest.DoesNotExist:
                return Response({'error': 'Interest not found'}, status=HTTPStatus.NOT_FOUND)

        # Pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10  # Set the number of items per page
        result_page = paginator.paginate_queryset(visions, request)

        serializer = VisionSerializer(result_page, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([AllowAny])
def get_vision_comments(request, vision_id):
    try:
        # Check if the vision exists
        vision = Vision.objects.get(pk=vision_id)
        
        # Get all comments for this vision
        comments = Comment.objects.filter(vision=vision, parent_comment=None).order_by('-created_at')
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10  # You can adjust this number as needed
        
        # Paginate the results
        paginated_comments = paginator.paginate_queryset(comments, request)
        
        # Serialize the paginated comments
        serializer = CommentSerializer(paginated_comments, many=True, context={'request': request})
        
        # Return the paginated response
        return Response({
            'data': serializer.data,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'count': paginator.page.paginator.count
        })
    
    except Vision.DoesNotExist:
        return Response({'error': 'Vision not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_comment_replies(request, comment_id):
    try:
        # Check if the parent comment exists
        parent_comment = Comment.objects.get(pk=comment_id)
        
        # Get all replies for this comment
        replies = Comment.objects.filter(parent_comment=parent_comment).order_by('created_at')
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10  # You can adjust this number as needed
        
        # Paginate the results
        paginated_replies = paginator.paginate_queryset(replies, request)
        
        # Serialize the paginated replies
        serializer = CommentSerializer(paginated_replies, many=True, context={'request': request})
        
        # Return the paginated response
        return Response({
            'data': serializer.data,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'count': paginator.page.paginator.count
        })
    
    except Comment.DoesNotExist:
        print('Parent comment not found')
        return Response({'error': 'Parent comment not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_poll(request):
    vision_id = request.data.get('vision_id')
    try:
        vision = Vision.objects.get(id=vision_id)
    except Vision.DoesNotExist:
        return Response({"error": "Vision not found"}, status=HTTPStatus.NOT_FOUND)

    serializer = PollSerializer(data=request.data)
    if serializer.is_valid():
        poll = serializer.save(vision=vision)
        
        # Write to Firestore
        db = firestore.client()
        db.collection('active_polls').document(str(poll.id)).set({
            'poll_id': poll.id,
            'question': poll.question,
            'items': [{'id': item.id, 'text': item.text, 'votes': 0} for item in poll.items.all()],
            'total_votes': 0,
            'created_at': firestore.SERVER_TIMESTAMP
        })
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_poll_details(request, poll_id):
    try:
        poll = Poll.objects.get(id=poll_id)
        serializer = PollSerializer(poll)
        return Response(serializer.data)
    except Poll.DoesNotExist:
        return Response({"error": "Poll not found"}, status=HTTPStatus.NOT_FOUND)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@transaction.atomic
def submit_poll_vote(request):
    poll_item_id = request.data.get('poll_item_id')
    user = request.user

    try:
        poll_item = PollItem.objects.select_related('poll').get(id=poll_item_id)
    except PollItem.DoesNotExist:
        return Response({"error": "Poll item not found"}, status=HTTPStatus.NOT_FOUND)

    # Check if user has already voted on this poll
    if Vote.objects.filter(poll_item__poll=poll_item.poll, user=user).exists():
        return Response({"error": "You have already voted on this poll"}, status=status.HTTP_400_BAD_REQUEST)

    # Create the vote
    Vote.objects.create(poll_item=poll_item, user=user)

    # Increment the vote count
    poll_item.votes += 1
    poll_item.save()

    # Update Firestore with new poll results
    update_firestore_poll_results(poll_item.poll)

    return Response({"message": "Vote submitted successfully"}, status=status.HTTP_201_CREATED)

def update_firestore_poll_results(poll):
    db = firestore.client()
    poll_ref = db.collection('active_polls').document(str(poll.id))
    
    poll_items = poll.items.all()
    total_votes = sum(item.votes for item in poll_items)
    
    poll_ref.update({
        'total_votes': total_votes,
        'items': [{
            'id': item.id,
            'votes': item.votes,
            'percentage': (item.votes / total_votes * 100) if total_votes > 0 else 0
        } for item in poll_items]
    })

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_invite(request):
    creator_id = request.data.get('creator_id')
    vision_id = request.data.get('vision_id')
    user = request.user

    try:
        creator = Creator.objects.get(pk=creator_id)
    except Creator.DoesNotExist:
        return Response({"message": "Creator not found"}, status=HTTPStatus.NOT_FOUND)

    try:
        vision = Vision.objects.get(pk=vision_id) if vision_id else None
    except Vision.DoesNotExist:
        return Response({"message": "Vision not found"}, status=HTTPStatus.NOT_FOUND)

    # Check if invite already exists
    if Invite.objects.filter(sender=user, creator=creator, status='pending', vision=vision).exists():
        return Response({"message": "Invite already sent"}, status=status.HTTP_400_BAD_REQUEST)

    # Create the invite
    invite = Invite.objects.create(sender=user, creator=creator, vision=vision)

    #TODO You might want to send a notification to the creator here

    return Response({"message": "Invite sent successfully"}, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def cancel_invite(request):
    creator_id = request.data.get('creator_id')
    user = request.user

    try:
        creator = Creator.objects.get(pk=creator_id)
    except Creator.DoesNotExist:
        return Response({"error": "Creator not found"}, status=HTTPStatus.NOT_FOUND)

    try:
        invite = Invite.objects.get(sender=user, recipient=creator, status='pending')
    except Invite.DoesNotExist:
        return Response({"error": "Invite not found"}, status=HTTPStatus.NOT_FOUND)

    # Delete the invite
    invite.delete()

    return Response({"message": "Invite cancelled successfully"}, status=status.HTTP_200_OK)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_invites(request):
    user = request.user
    invites = Invite.objects.filter(recipient=user, status='pending')
    
    serializer = InviteSerializer(invites, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def respond_to_invite(request):
    invite_id = request.data.get('invite_id')
    response = request.data.get('response')  # 'accept' or 'reject'
    user = request.user

    try:
        invite = Invite.objects.get(pk=invite_id, recipient=user, status='pending')
    except Invite.DoesNotExist:
        return Response({"error": "Invite not found"}, status=HTTPStatus.NOT_FOUND)

    if response == 'accept':
        invite.status = 'accepted'
        invite.save()
        # Here you might want to start a stream or update the stream status
        return Response({"message": "Invite accepted"}, status=status.HTTP_200_OK)
    elif response == 'reject':
        invite.status = 'rejected'
        invite.save()
        return Response({"message": "Invite rejected"}, status=status.HTTP_200_OK)
    else:
        return Response({"error": "Invalid response"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_filtered_visions(request, creator_id):
    try:
        # Get query parameters from request body
        data = request.data
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        drafts_only = data.get('drafts_only', False)
        sort_by = data.get('sort_by', 'Newest')
        search_query = data.get('search', '')
        hashtags = data.get('hashtags', [])
        page = int(data.get('page', 1))

        # Start with all visions for the creator
        visions = Vision.objects.filter(creator_id=creator_id)

        # Apply text search if provided
        if search_query:
            visions = visions.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        # Apply hashtag filter if provided
        if hashtags:
            visions = visions.filter(interests__name__in=hashtags)

        # Apply date range filter if provided
        if start_date:
            visions = visions.filter(created_at__gte=start_date)
        if end_date:
            visions = visions.filter(created_at__lte=end_date)

        # Apply drafts only filter if true
        if drafts_only:
            visions = visions.filter(is_draft=True)

        # Apply sorting
        if sort_by == 'Oldest':
            visions = visions.order_by('created_at')
        elif sort_by == 'Most Views':
            visions = visions.order_by('-views')
        elif sort_by == 'Most Likes':
            visions = visions.order_by('-likes')
        elif sort_by == 'Most Tips':
            visions = visions.order_by('-tips_received')
        else:  # Default to 'Newest'
            visions = visions.order_by('-created_at')

        # Paginate results
        paginator = Paginator(visions, 10)  # 10 items per page
        paginated_visions = paginator.get_page(page)

        serializer = VisionSerializer(paginated_visions, many=True, context={'request': request})

        return Response({
            'results': serializer.data,
            'page': page,
            'total_pages': paginator.num_pages,
            'total_results': paginator.count,
        })

    except Exception as e:
        return Response({
            'error': True,
            'message': f'Error getting filtered visions: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

def is_suspicious_activity(user_id, ip_address):
    """
    Check if the user or IP shows signs of bot-like behavior
    """
    # Check for rapid viewing patterns from this IP
    recent_ip_views = ViewCount.objects.filter(
        ip_address=ip_address,
        timestamp__gte=timezone.now() - timezone.timedelta(hours=1)
    ).count()
    
    # Check for views across many videos from the same IP
    unique_visions_from_ip = ViewCount.objects.filter(
        ip_address=ip_address,
        timestamp__gte=timezone.now() - timezone.timedelta(hours=1)
    ).values('vision').distinct().count()
    
    # Check for views across many users from the same IP (potential proxy/VPN)
    unique_users_from_ip = ViewCount.objects.filter(
        ip_address=ip_address,
        timestamp__gte=timezone.now() - timezone.timedelta(hours=1)
    ).values('user').distinct().count()
    
    # Define thresholds for suspicious activity
    if recent_ip_views > 50:  # Too many views in past hour
        return True
    
    if unique_visions_from_ip > 30:  # Too many different videos from same IP
        return True
        
    if unique_users_from_ip > 5:  # Too many different users from same IP
        return True
        
    return False

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_view(request, vision_pk):
    try:
        # First, just get the vision with minimal data to confirm it exists
        vision = Vision.objects.get(pk=vision_pk)
        
        # Get user from database
        user = User.objects.get(pk=request.user.pk)
        
        # Get client IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Validate view duration
        view_duration = request.data.get('duration', 30)
        min_duration_required = 10  # Minimum 10 seconds to count as a view
        
        if view_duration < min_duration_required:
            return Response({
                'message': 'View duration too short'
            }, status=status.HTTP_200_OK)
        
        # Rate limiting: Check if user has added views recently
        recent_views = ViewCount.objects.filter(
            user=user,
            timestamp__gte=timezone.now() - timezone.timedelta(minutes=5)
        ).count()
        
        if recent_views > 10:  # Limit to 10 views per 5 minutes
            return Response({
                'message': 'Rate limit reached'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        
        # Determine if the activity is suspicious
        is_suspicious = is_suspicious_activity(user.id, ip)
        
        # Always record the view in the ViewCount table
        view_entry = ViewCount.objects.create(
            user=user,
            vision=vision,
            ip_address=ip,
            view_duration=view_duration,
            is_valid=not is_suspicious  # Mark as invalid if suspicious
        )
        
        # Log suspicious activity for review
        if is_suspicious:
            logger.warning(f"Suspicious view activity detected: User {user.id}, IP {ip}")
            
            # Return success response but don't increment view count
            return Response({
                'message': 'View recorded'
            }, status=status.HTTP_200_OK)
        
        # Add to watch history if not already there (for UI purposes)
        if not WatchHistory.objects.filter(user=user, vision=vision).exists():
            WatchHistory.objects.create(
                user=user,
                vision=vision,
                ip_address=ip,
                view_duration=view_duration
            )
            
        # Increment the vision's view count (only for valid views)
        Vision.objects.filter(pk=vision.pk).update(views=models.F('views') + 1)
        
        return Response({
            'message': 'View count update queued successfully'
        }, status=status.HTTP_200_OK)
        
    except Vision.DoesNotExist:
        return Response({
            'error': 'Vision not found'
        }, status=HTTPStatus.NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error queueing view count update: {e}")
        return Response({
            'error': 'An error occurred while processing view'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def encoding(request):
    try:
        # Get all visions with transcoding status for the authenticated user
        encoding_visions = Vision.with_locks.with_is_locked(request.user).filter(
            status='transcoding',
            creator__user=request.user
        ).order_by('-created_at')
        
        # Serialize the visions
        serializer = VisionSerializer(encoding_visions, many=True, context={'request': request})
        
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting encoding visions: {e}")
        return Response({
            'error': True,
            'message': f'Error getting encoding visions: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def encode(request, vision_pk):
    try:
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_pk)
        
        # Update vision status to transcoding
        vision.status = 'transcoding'
        vision.save()
        
        return Response({
            'message': 'Vision status updated to transcoding successfully',
            'vision': VisionSerializer(vision, context={'request': request}).data
        }, status=status.HTTP_200_OK)
        
    except Vision.DoesNotExist:
        return Response({
            'error': True,
            'message': 'Vision not found'
        }, status=HTTPStatus.NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error updating vision status to transcoding: {e}")
        return Response({
            'error': True,
            'message': f'Error updating vision status: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_interactive_story(request):
    try:
        # Extract data from request
        title = request.data.get('title')
        description = request.data.get('description')
        hashtags = request.data.get('hashtags', '').split(',')
        nodes_data = json.loads(request.data.get('nodes', '[]'))
        access_type = request.data.get('access_type', 'free')
        ppv_price = request.data.get('price_credits', 0)
        aspect_ratio = request.data.get('aspect_ratio', '16:9')
        stereo_mapping = request.data.get('stereo_mapping', 'normal')

        # Check if this is for a vision request
        vision_request_id = request.data.get('vision_request_id')
        vision_request = None
        if vision_request_id:
            try:
                vision_request = VisionRequest.objects.get(pk=vision_request_id)
                # Verify the user is the creator of the request
                if vision_request.creator.user != request.user:
                    return Response({
                        'error': 'You do not have permission to create vision for this request'
                    }, status=HTTPStatus.FORBIDDEN)
                # Verify request is in accepted status
                if vision_request.status != 'accepted':
                    return Response({
                        'error': 'Can only create vision for accepted requests'
                    }, status=status.HTTP_400_BAD_REQUEST)
            except VisionRequest.DoesNotExist:
                return Response({
                    'error': 'Vision request not found'
                }, status=HTTPStatus.NOT_FOUND)

        # Create the vision instance with story graph
        processed_nodes = []
        for node in nodes_data:
            node_data = {
                'id': str(node.get('id')),
                'video_url': node.get('video_url', ''),
                'is_local_video': node.get('is_local_video', True),
                'question': node.get('question', ''),
                'options': [
                    {
                        'id': str(opt.get('pk')),
                        'text': opt.get('text', ''),
                        'next_node': opt.get('next_node', '')
                    }
                    for opt in node.get('options', [])
                ]
            }
            processed_nodes.append(node_data)

        # Create vision instance
        vision = Vision.objects.create(
            creator=Creator.objects.get(user=request.user),
            status='transcoding',
            is_interactive=True,
            private_user=vision_request.requester if vision_request else None,
            vision_request=vision_request,
            access_type=access_type,
            ppv_price=ppv_price,
            title=title,
            description=description,
            aspect_ratio=aspect_ratio,
            stereo_mapping=stereo_mapping,
            story_graph={'nodes': processed_nodes}
        )

        # Handle thumbnail upload if provided
        if 'thumbnail' in request.FILES:
            try:
                thumbnail_res = cloudinary.uploader.upload(
                    request.FILES['thumbnail'],
                    public_id=f'{request.user.username}-{vision.pk}-thumbnail',
                    unique_filename=False,
                    overwrite=True
                )
                vision.thumbnail = thumbnail_res['secure_url']
                vision.save()
            except Exception as e:
                logger.error(f"Error uploading thumbnail: {e}")
                # Continue execution even if thumbnail upload fails

        # Add interests (hashtags)
        for hashtag in hashtags:
            if hashtag.strip():
                interest, _ = Interest.objects.get_or_create(name=hashtag.strip())
                vision.interests.add(interest)

        return Response({
            'id': vision.id,
            'message': 'Interactive story created successfully',
            'story_nodes': processed_nodes,
            'thumbnail_url': vision.thumbnail
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error creating interactive story: {e}")
        return Response({
            'error': True,
            'message': f'Error creating interactive story: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_interactive_story_node(request):
    try:
        # Extract data from request
        node_data = request.data.get('node_data', {})
        options_data = request.data.get('options', [])
        vision_id = request.data.get('vision_id')

        # Validate vision_id is provided
        if not vision_id:
            return Response({
                'error': True,
                'message': 'vision_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get vision object
        try:
            vision = Vision.objects.get(id=vision_id)
        except Vision.DoesNotExist:
            return Response({
                'error': True,
                'message': 'Vision not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Initialize Backblaze B2 client
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account("production", os.environ.get("B2_KEY_ID"), os.environ.get("B2_APPLICATION_KEY"))
        b2_bucket = b2_api.get_bucket_by_name(os.environ.get("B2_BUCKET_NAME"))
        
        filename = f'{request.user.username}-{node_data.get("id", "")}-node-{timezone.now().timestamp()}.mp4'

        # Get upload URL and authorization token
        upload_auth = b2_api.session.get_upload_url(b2_bucket.get_id())
        upload_url = upload_auth['uploadUrl'] 
        upload_auth_token = upload_auth['authorizationToken']

        # Create a temporary video URL that will be updated after B2 upload
        file_url = f"b2://{os.environ.get('B2_BUCKET_NAME')}/{filename}"

        # Create the story node
        story_node = StoryNode.objects.create(
            vision=vision,
            video_url=file_url,
            question=node_data.get('question', ''),
            is_local_video=True
        )

        # Create options for the node
        for option_data in options_data:
            StoryOption.objects.create(
                node=story_node,
                text=option_data.get('text', ''),
                video_url=option_data.get('videoUrl', ''),
                is_local_video=option_data.get('isLocalVideo', True)
            )

        # Generate download URL
        download_url = f"https://{os.environ.get('B2_DOWNLOAD_URL')}/file/{os.environ.get('B2_BUCKET_NAME')}/{filename}"

        # Return the B2 data for form submission
        return Response({
            'id': story_node.pk,
            'get_url': download_url,
            'b2data': {
                'uploadUrl': upload_url,
                'authorizationToken': upload_auth_token,
                'fileName': filename,
                'bucketName': os.environ.get('B2_BUCKET_NAME'),
                'contentType': 'video/mp4'
            }
        })

    except Exception as e:
        logger.error(f"Error creating interactive story node: {e}")
        return Response({
            'error': True,
            'message': f'Error creating interactive story node: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_node_upload_url(request, vision_id, node_id):
    try:
        # Debug authentication
        logger.info(f"Auth header: {request.headers.get('Authorization')}")
        logger.info(f"User: {request.user}")
        logger.info(f"User is authenticated: {request.user.is_authenticated}")

        if not request.user.is_authenticated:
            return Response({
                'error': True,
                'message': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Validate vision exists
        try:
            # Get vision and creator user id directly from the database
            vision = Vision.objects.select_related('creator__user').get(id=vision_id)
            creator_user_id = vision.creator.user_id if vision.creator else None
            
            # Check permission only if creator exists and is not the requesting user
            if creator_user_id and creator_user_id != request.user.id:
                return Response({
                    'error': True,
                    'message': 'You do not have permission to access this vision'
                }, status=HTTPStatus.FORBIDDEN)
                
        except Vision.DoesNotExist:
            return Response({
                'error': True,
                'message': 'Vision not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Initialize Backblaze B2 client
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account("production", os.environ.get("B2_KEY_ID"), os.environ.get("B2_APPLICATION_KEY"))
        b2_bucket = b2_api.get_bucket_by_name(os.environ.get("B2_BUCKET_NAME"))
        
        filename = f'{request.user.username}-{vision_id}-{node_id}-{timezone.now().timestamp()}.mp4'

        # Get upload URL and authorization token
        upload_auth = b2_api.session.get_upload_url(b2_bucket.get_id())
        upload_url = upload_auth['uploadUrl'] 
        upload_auth_token = upload_auth['authorizationToken']

        # Generate download URL
        download_url = f"https://{os.environ.get('B2_DOWNLOAD_URL')}/file/{os.environ.get('B2_BUCKET_NAME')}/{filename}"

        # Return the B2 data for form submission
        return Response({
            'get_url': download_url,
            'b2data': {
                'uploadUrl': upload_url,
                'authorizationToken': upload_auth_token,
                'fileName': filename,
                'bucketName': os.environ.get('B2_BUCKET_NAME'),
                'contentType': 'video/mp4'
            }
        })

    except Exception as e:
        logger.error(f"Error getting node upload URL: {e}")
        logger.error(f"Request headers: {request.headers}")
        return Response({
            'error': True,
            'message': f'Error getting node upload URL: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_option_upload_url(request, vision_id, node_id, option_id):
    """Get a pre-signed S3 URL for uploading an option video"""
    try:
        try:
            vision = Vision.objects.get(pk=vision_id)
            creator_user_id = vision.creator.user.id if vision.creator else None
            
            # Check permission only if creator exists and is not the requesting user
            if creator_user_id and creator_user_id != request.user.id:
                return Response({
                    'error': True,
                    'message': 'You do not have permission to access this vision'
                }, status=HTTPStatus.FORBIDDEN)
                
        except Vision.DoesNotExist:
            return Response({
                'error': True,
                'message': 'Vision not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Initialize Backblaze B2 client
        info = b2.InMemoryAccountInfo()
        b2_api = b2.B2Api(info)
        b2_api.authorize_account("production", os.environ.get("B2_KEY_ID"), os.environ.get("B2_APPLICATION_KEY"))
        b2_bucket = b2_api.get_bucket_by_name(os.environ.get("B2_BUCKET_NAME"))
        
        filename = f'{request.user.username}-{vision_id}-{node_id}-{option_id}-{timezone.now().timestamp()}.mp4'

        # Get upload URL and authorization token
        upload_auth = b2_api.session.get_upload_url(b2_bucket.get_id())
        upload_url = upload_auth['uploadUrl'] 
        upload_auth_token = upload_auth['authorizationToken']

        # Generate download URL
        download_url = f"https://{os.environ.get('B2_DOWNLOAD_URL')}/file/{os.environ.get('B2_BUCKET_NAME')}/{filename}"

        # Return the B2 data for form submission
        return Response({
            'get_url': download_url,
            'b2data': {
                'uploadUrl': upload_url,
                'authorizationToken': upload_auth_token,
                'fileName': filename,
                'bucketName': os.environ.get('B2_BUCKET_NAME'),
                'contentType': 'video/mp4'
            }
        })

    except Exception as e:
        logger.error(f"Error getting option upload URL: {e}")
        logger.error(f"Request headers: {request.headers}")
        return Response({
            'error': True,
            'message': f'Error getting option upload URL: {str(e)}'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_for_me_visions(request, creator_pk):
    try:
        # Get visions where the authenticated user is the private_user and matches the creator
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            private_user=request.user,
            creator_id=creator_pk
        ).order_by('-created_at')
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)
        
        # Serialize and return the results
        return paginator.get_paginated_response(VisionSerializer(results, many=True, context={'request': request}).data)
    except Exception as e:
        logger.error(f"Error getting creator for me visions: {e}")
        return Response({
            'error': True,
            'message': f'Error getting creator for me visions: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_highlights_visions(request, creator_pk):
    try:
        # Get visions where is_highlight is True and matches the creator
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            is_highlight=True,
            creator_id=creator_pk
        ).filter(status__in=['vod', 'live']).order_by('-created_at')
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)
        
        # Serialize and return the results
        return paginator.get_paginated_response(VisionSerializer(results, many=True, context={'request': request}).data)
    except Exception as e:
        logger.error(f"Error getting creator highlights visions: {e}")
        return Response({
            'error': True,
            'message': f'Error getting creator highlights visions: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_comment(request, vision_id):
    try:
        print('vision_id:', vision_id)
        # Get the vision
        vision = Vision.objects.get(pk=vision_id)
        
        # Get user from pk and create comment
        user = User.objects.get(pk=request.user.pk)
        comment = Comment.objects.create(
            user=user,
            vision=vision, 
            text=request.data.get('text', '')
        )
        
        # Serialize and return the comment
        serializer = CommentSerializer(comment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Vision.DoesNotExist:
        print('Vision not found')
        return Response({
            'error': 'Vision not found'
        }, status=HTTPStatus.NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error creating comment: {e}")
        return Response({
            'error': 'An error occurred while creating the comment'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_comment_reply(request, comment_id):
    try:
        # Get the parent comment
        parent_comment = Comment.objects.get(pk=comment_id)
        
        # Get user from pk and create reply comment
        user = User.objects.get(pk=request.user.pk)
        reply = Comment.objects.create(
            user=user,
            vision=parent_comment.vision,
            text=request.data.get('text', ''),
            parent_comment=parent_comment
        )
        
        # Serialize and return the reply
        serializer = CommentSerializer(reply, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Comment.DoesNotExist:
        return Response({
            'error': 'Parent comment not found'
        }, status=HTTPStatus.NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error creating comment reply: {e}")
        return Response({
            'error': 'An error occurred while creating the comment reply'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_highlight(request):
    """
    Create a highlight from an existing vision
    """
    try:
        # Get vision_id from request body instead of URL
        vision_id = request.data.get('vision_id')
        if not vision_id:
            return Response({"error": "vision_id is required"}, 
                          status=status.HTTP_400_BAD_REQUEST)
            
        # Get the original vision
        vision = Vision.objects.get(pk=vision_id)
        
        # Validate input
        start_time = request.data.get('start_time')  # Already in seconds from frontend
        end_time = request.data.get('end_time')      # Already in seconds from frontend
        access_type = request.data.get('access_type', 'public')
        
        if start_time is None or end_time is None:
            return Response({"error": "start_time and end_time are required"}, 
                          status=status.HTTP_400_BAD_REQUEST)
            
        if not vision.url:
            return Response({"error": "Vision has no video URL"}, 
                          status=status.HTTP_400_BAD_REQUEST)
            
        # Create a pending highlight Vision object first
        highlight = Vision.objects.create(
            title=f"Highlight: {vision.title}",
            description=f"Highlight from {vision.title} ({start_time}s to {end_time}s)",
            thumbnail=vision.thumbnail,
            creator=vision.creator,
            is_highlight=True,
            stereo_mapping=vision.stereo_mapping,
            aspect_ratio=vision.aspect_ratio,
            status='transcoding',  # Set initial status as transcoding
            private_user=request.user if access_type == 'private' else None
        )

        # Set interests after creation
        highlight.interests.set(vision.interests.all())
        
        # Copy interests from original vision
        highlight.interests.set(vision.interests.all())
        
        # Make async request to streaming service
        # This will return immediately while processing continues in background
        streaming_service_url = f"{settings.STREAMING_SERVICE_URL}/api/create-highlight"
        response = requests.post(streaming_service_url, json={
            'video_url': vision.url,  # Pass the full URL from the Vision model
            'start_time': start_time,
            'end_time': end_time,
            'highlight_id': highlight.pk  # Pass highlight ID for callback
        }, timeout=10)  # Set a reasonable timeout for the initial request

        print('Streaming service response:', response.json())
        
        if response.status_code != 200:
            highlight.status = 'failed'
            highlight.save()
            print('Failed to initiate highlight creation')
            return Response({"error": "Failed to initiate highlight creation"}, 
                          status=HTTPStatus.INTERNAL_SERVER_ERROR)
            
        # Return the pending highlight data
        return Response({
            'id': highlight.pk,
            'title': highlight.title,
            'status': highlight.status,
            'message': 'Highlight creation started. You will be notified when it is ready.',
            'creator': highlight.creator.user.username,
            'created_at': highlight.created_at
        })
        
    except Vision.DoesNotExist:
        return Response({"error": "Vision not found"}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        print('Error creating highlight:', e)
        logger.error(f"Error creating highlight: {str(e)}")
        return Response({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def highlight_complete(request):
    """
    Callback endpoint for when highlight processing is complete
    """
    api_key = request.data.get('api_key')
    if api_key != settings.NGINX_API_KEY:
        return Response({"error": "Unauthorized"}, status=401)
        
    highlight_id = request.data.get('highlight_id')
    hls_url = request.data.get('hls_url')
    success = request.data.get('success', False)

    print('highlight_id:', highlight_id)
    print('hls_url:', hls_url)
    print('success:', success)
    
    try:
        highlight = Vision.objects.get(pk=highlight_id)
        
        if success:
            highlight.url = settings.FILE_HOST + hls_url
            highlight.status = 'vod'
        else:
            highlight.status = 'failed'
            
        highlight.save()
        
        # Notify the user
        try:
            send_fcm_notification(
                highlight.creator.user,
                "Highlight Processing Complete",
                f"Your highlight '{highlight.title}' is now ready to view" if success else f"Failed to create highlight '{highlight.title}'",
                data={
                    'vision_id': str(highlight.id),
                    'status': highlight.status
                }
            )
        except Exception as e:
            logger.error(f"Failed to send highlight notification: {e}")
            
        return Response({'message': 'Successfully updated highlight status'})
        
    except Vision.DoesNotExist:
        return Response({'error': 'Highlight not found'}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        logger.error(f"Error completing highlight: {str(e)}")
        return Response({'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def update_vision_access(request, vision_pk):
    """
    Update the access type of a vision
    """
    try:
        # Get the vision and verify ownership
        vision = Vision.with_locks.with_is_locked(request.user).get(pk=vision_pk)
        
        # Verify the user is the creator
        if vision.creator.user != request.user:
            return Response({
                'error': 'You do not have permission to modify this vision'
            }, status=HTTPStatus.FORBIDDEN)
        
        # Get access type from request
        access_type = request.data.get('access_type')
        
        # Validate access type
        if access_type not in [choice[0] for choice in Vision.ACCESS_TYPE_CHOICES]:
            return Response({
                'error': 'Invalid access type. Must be either "free" or "premium"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update access type
        vision.access_type = access_type
        vision.save()
        
        return Response({
            'message': 'Vision access type updated successfully',
            'vision': VisionSerializer(vision, context={'request': request}).data
        })
        
    except Vision.DoesNotExist:
        return Response({
            'error': 'Vision not found'
        }, status=HTTPStatus.NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error updating vision access type: {e}")
        return Response({
            'error': 'An error occurred while updating vision access type'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def create_vision_request(request):
    """
    Create a new vision request from a user to a creator
    """
    try:
        creator_id = request.data.get('creator_id')
        if not creator_id:
            return Response({
                'error': 'creator_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get creator
        try:
            creator = Creator.objects.get(pk=creator_id)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)
        
        # Get user from database
        user = User.objects.get(pk=request.user.pk)
        
        # Create vision request
        vision_request = VisionRequest.objects.create(
            requester=user,
            creator=creator,
            title=request.data.get('title', ''),
            description=request.data.get('description', ''),
            budget=request.data.get('budget'),
            deadline=request.data.get('deadline')
        )

        # Send notification to creator
        try:
            send_fcm_notification(
                creator.user,
                'New Vision Request',
                f'{request.user.username} has requested a private vision',
                {
                    'request_id': str(vision_request.id),
                    'type': 'new_vision_request'
                }
            )
        except Exception as e:
            logger.error(f"Failed to send vision request notification: {e}")

        return Response({
            'message': 'Vision request created successfully',
            'request_id': vision_request.id
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Error creating vision request: {e}")
        return Response({
            'error': 'An error occurred while creating the vision request'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_vision_requests(request):
    """
    Get vision requests for the authenticated user
    If user is a creator, returns received requests
    If user is a spectator, returns sent requests
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Check if user is a creator
        try:
            creator = Creator.objects.get(user=user)
            # Use select_related to optimize queries
            vision_requests = VisionRequest.objects.select_related(
                'requester',
                'creator',
                'creator__user',
                'vision'
            ).filter(creator=creator)
        except Creator.DoesNotExist:
            # User is a spectator, get their sent requests
            vision_requests = VisionRequest.objects.select_related(
                'requester',
                'creator',
                'creator__user',
                'vision'
            ).filter(requester=user)

        # Apply filters if provided
        status_filter = request.GET.get('status')
        if status_filter:
            vision_requests = vision_requests.filter(status=status_filter)

        # Order by created_at descending (newest first)
        vision_requests = vision_requests.order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(vision_requests, request)

        # Serialize the results
        data = [{
            'id': req.id,
            'title': req.title,
            'description': req.description,
            'status': req.status,
            'budget': str(req.budget) if req.budget else None,
            'deadline': req.deadline.isoformat() if req.deadline else None,
            'created_at': req.created_at.isoformat(),
            'requester': {
                'id': req.requester.pk,
                'username': req.requester.username,
                'profile_picture': req.requester.profile_picture_url
            },
            'creator': {
                'id': req.creator.pk,
                'username': req.creator.user.username,
                'profile_picture': req.creator.user.profile_picture_url
            },
            'vision': {
                'id': req.vision.id,
                'title': req.vision.title,
                'url': req.vision.url,
                'thumbnail': req.vision.thumbnail
            } if req.vision else None
        } for req in results]

        return paginator.get_paginated_response(data)

    except Exception as e:
        logger.error(f"Error getting vision requests: {e}")
        return Response({
            'error': 'An error occurred while getting vision requests'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def respond_to_vision_request(request, request_id):
    """
    Accept or reject a vision request
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Get the vision request
        try:
            vision_request = VisionRequest.objects.get(pk=request_id)
        except VisionRequest.DoesNotExist:
            return Response({
                'error': 'Vision request not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Verify the user is the creator
        if vision_request.creator.user != user:
            return Response({
                'error': 'You do not have permission to respond to this request'
            }, status=HTTPStatus.FORBIDDEN)

        # Get response type
        response_type = request.data.get('response')
        if response_type not in ['accept', 'reject']:
            return Response({
                'error': 'Invalid response type. Must be either "accept" or "reject"'
            }, status=status.HTTP_400_BAD_REQUEST)

        if response_type == 'accept':
            # Handle credit transfer if there's a budget
            if vision_request.budget:
                try:
                    with transaction.atomic():
                        # Get or create credit balances
                        requester_balance, _ = CreditBalance.objects.get_or_create(user=vision_request.requester)
                        creator_balance, _ = CreditBalance.objects.get_or_create(user=vision_request.creator.user)

                        # Convert budget to credits (assuming 1:1 ratio)
                        credits = int(vision_request.budget)

                        # Check if requester has sufficient credits
                        if requester_balance.spectator_balance < credits:
                            return Response({
                                'error': 'Requester has insufficient credits',
                                'required_credits': credits,
                                'current_balance': requester_balance.spectator_balance
                            }, status=status.HTTP_400_BAD_REQUEST)

                        # Transfer credits
                        requester_balance.deduct_spectator_credits(credits)
                        creator_balance.add_creator_credits(credits)

                        # Record credit transactions
                        CreditTransaction.objects.create(
                            user=vision_request.requester,
                            amount=-credits,
                            transaction_type='vision_request',
                            metadata={
                                'vision_request_id': str(vision_request.id),
                                'recipient_id': str(vision_request.creator.user.id)
                            }
                        )

                        CreditTransaction.objects.create(
                            user=vision_request.creator.user,
                            amount=credits,
                            transaction_type='vision_request',
                            metadata={
                                'vision_request_id': str(vision_request.id),
                                'sender_id': str(vision_request.requester.id)
                            }
                        )

                        # Update request status
                        vision_request.status = 'accepted'
                        vision_request.save()

                        # Send notification to requester
                        try:
                            send_fcm_notification(
                                vision_request.requester,
                                'Vision Request Accepted',
                                f'{user.username} has accepted your vision request',
                                {
                                    'request_id': str(vision_request.id),
                                    'type': 'vision_request_accepted',
                                    'credits_transferred': credits
                                }
                            )
                        except Exception as e:
                            logger.error(f"Failed to send vision request acceptance notification: {e}")

                except Exception as e:
                    logger.error(f"Error processing credit transfer: {e}")
                    return Response({
                        'error': 'An error occurred while processing the credit transfer'
                    }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            else:
                # If no budget, just update status
                vision_request.status = 'accepted'
                vision_request.save()

                # Send notification to requester
                try:
                    send_fcm_notification(
                        vision_request.requester,
                        'Vision Request Accepted',
                        f'{user.username} has accepted your vision request',
                        {
                            'request_id': str(vision_request.id),
                            'type': 'vision_request_accepted'
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to send vision request acceptance notification: {e}")
        else:
            # Reject the request
            vision_request.status = 'rejected'
            vision_request.save()

            # Send notification to requester
            try:
                send_fcm_notification(
                    vision_request.requester,
                    'Vision Request Rejected',
                    f'{user.username} has rejected your vision request',
                    {
                        'request_id': str(vision_request.id),
                        'type': 'vision_request_rejected'
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send vision request rejection notification: {e}")

        return Response({
            'message': f'Vision request {vision_request.status} successfully'
        })

    except Exception as e:
        logger.error(f"Error responding to vision request: {e}")
        return Response({
            'error': 'An error occurred while responding to the vision request'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def upload_requested_vision(request, request_id):
    """
    Upload a vision for an accepted request
    """
    try:
        # Get the vision request
        try:
            vision_request = VisionRequest.objects.get(pk=request_id)
        except VisionRequest.DoesNotExist:
            return Response({
                'error': 'Vision request not found'
            }, status=HTTPStatus.NOT_FOUND)
        
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Verify the user is the creator
        if vision_request.creator.user != user:
            return Response({
                'error': 'You do not have permission to upload for this request'
            }, status=HTTPStatus.FORBIDDEN)

        # Verify request is accepted
        if vision_request.status != 'accepted':
            return Response({
                'error': 'Can only upload vision for accepted requests'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Set up S3 client
        s3 = boto3.client('s3',
            region_name='us-east-1',
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        
        filename = f'{user.username}-request-{request_id}-{timezone.now().timestamp()}.mp4'

        # Generate presigned POST data
        s3_data = s3.generate_presigned_post(
            Bucket=os.environ.get('S3_BUCKET'),
            Key=filename,
            Fields={"acl": "public-read"},
            Conditions=[
                {"acl": "public-read"}
            ],
            ExpiresIn=3600
        )

        # Create vision instance
        vision = Vision.objects.create(
            title=vision_request.title,
            description=vision_request.description,
            creator=vision_request.creator,
            status='pending_upload',
            private_user=vision_request.requester
        )

        # Update vision request with vision reference
        vision_request.vision = vision
        vision_request.status = 'completed'
        vision_request.save()

        # Return the S3 data for form submission
        return Response({
            'vision_id': vision.id,
            'get_url': f"https://{os.environ.get('S3_BUCKET')}.s3.amazonaws.com/{filename}",
            's3data': {
                'url': s3_data['url'],
                'fields': s3_data['fields']
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error uploading requested vision: {e}")
        return Response({
            'error': 'An error occurred while uploading the vision'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_vision_requests(request, creator_id):
    """
    Get all vision requests for a specific creator
    Includes filtering options for status and date range
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Get creator
        try:
            creator = Creator.objects.get(pk=creator_id)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Verify the user is either the creator or the requester
        is_creator = creator.user == user
        
        # Base queryset with related fields to avoid N+1 queries
        vision_requests = VisionRequest.objects.select_related(
            'requester',
            'creator',
            'creator__user',
            'vision'
        ).filter(creator=creator)
        
        # If not the creator, only show requests from the current user
        if not is_creator:
            vision_requests = vision_requests.filter(requester=user)

        # Apply filters if provided
        status_filter = request.GET.get('status')
        if status_filter:
            vision_requests = vision_requests.filter(status=status_filter)

        start_date = request.GET.get('start_date')
        if start_date:
            vision_requests = vision_requests.filter(created_at__gte=start_date)

        end_date = request.GET.get('end_date')
        if end_date:
            vision_requests = vision_requests.filter(created_at__lte=end_date)

        # Order by created_at descending (newest first)
        vision_requests = vision_requests.order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(vision_requests, request)

        # Serialize the results
        data = [{
            'id': req.id,
            'title': req.title,
            'description': req.description,
            'status': req.status,
            'budget': str(req.budget) if req.budget else None,
            'deadline': req.deadline.isoformat() if req.deadline else None,
            'created_at': req.created_at.isoformat(),
            'requester': {
                'id': req.requester.pk,
                'username': req.requester.username,
                'profile_picture': req.requester.profile_picture_url
            },
            'creator': {
                'id': req.creator.pk,
                'username': req.creator.user.username,
                'profile_picture': req.creator.user.profile_picture_url
            },
            'vision': {
                'id': req.vision.id,
                'title': req.vision.title,
                'url': req.vision.url,
                'thumbnail': req.vision.thumbnail
            } if req.vision else None
        } for req in results]

        return paginator.get_paginated_response(data)

    except Exception as e:
        logger.error(f"Error getting creator vision requests: {e}")
        return Response({
            'error': 'An error occurred while getting vision requests'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def cancel_vision_request(request, request_id):
    """
    Cancel a vision request
    Only the requester can cancel their request, and only if it's in pending or accepted status
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Get the vision request
        try:
            vision_request = VisionRequest.objects.get(pk=request_id)
        except VisionRequest.DoesNotExist:
            return Response({
                'error': 'Vision request not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Verify the user is the requester
        if vision_request.requester != user:
            return Response({
                'error': 'You do not have permission to cancel this request'
            }, status=HTTPStatus.FORBIDDEN)

        # Check if request can be cancelled
        if vision_request.status not in ['pending', 'accepted']:
            return Response({
                'error': f'Cannot cancel request in {vision_request.status} status'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update request status to cancelled
        vision_request.status = 'cancelled'
        vision_request.save()

        # Send notification to creator
        try:
            send_fcm_notification(
                vision_request.creator.user,
                'Vision Request Cancelled',
                f'{user.username} has cancelled their vision request',
                {
                    'request_id': str(vision_request.id),
                    'type': 'vision_request_cancelled'
                }
            )
        except Exception as e:
            logger.error(f"Failed to send vision request cancellation notification: {e}")

        return Response({
            'message': 'Vision request cancelled successfully',
            'request': {
                'id': vision_request.id,
                'title': vision_request.title,
                'status': vision_request.status,
                'created_at': vision_request.created_at.isoformat(),
                'requester': {
                    'id': vision_request.requester.pk,
                    'username': vision_request.requester.username,
                    'profile_picture': vision_request.requester.profile_picture_url
                },
                'creator': {
                    'id': vision_request.creator.pk,
                    'username': vision_request.creator.user.username,
                    'profile_picture': vision_request.creator.user.profile_picture_url
                }
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error cancelling vision request: {e}")
        return Response({
            'error': 'An error occurred while cancelling the vision request'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_private_visions(request, creator_pk):
    """
    Get all private visions for a specific creator where the authenticated user is the private user
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Get creator
        try:
            creator = Creator.objects.get(pk=creator_pk)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Get all visions where user is the private user and creator matches
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            creator=creator,
            private_user=user,
            status__in=['vod', 'live']
        ).select_related(
            'creator',
            'creator__user',
            'vision_request'
        ).prefetch_related(
            'interests'
        ).order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)

        # Serialize the results
        serializer = VisionSerializer(results, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error getting private visions: {e}")
        return Response({
            'error': 'An error occurred while getting private visions'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_highlighted_visions(request, creator_pk):
    """
    Get all highlighted visions for a specific creator
    """
    try:
        # Get user from database
        user = User.objects.get(pk=request.user.pk)

        # Get creator
        try:
            creator = Creator.objects.get(pk=creator_pk)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Get all visions where creator matches and is_highlight is True
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            creator=creator,
            is_highlight=True,
            status__in=['vod', 'live']
        ).select_related(
            'creator',
            'creator__user',
            'vision_request'
        ).prefetch_related(
            'interests'
        ).order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)

        # Serialize the results
        serializer = VisionSerializer(results, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error getting highlighted visions: {e}")
        return Response({
            'error': 'An error occurred while getting highlighted visions'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def send_request_chat_notification(request, request_id):
    """
    Send FCM notification for new chat messages in a vision request.
    
    Required POST data:
    - message: The chat message content
    """
    try:
        # Get the vision request
        try:
            vision_request = VisionRequest.objects.select_related(
                'creator__user',
                'requester'
            ).get(pk=request_id)
        except VisionRequest.DoesNotExist:
            return Response({
                'error': 'Vision request not found'
            }, status=HTTPStatus.NOT_FOUND)

        message = request.data.get('message')
        if not message:
            return Response({
                'error': 'Message is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Determine the recipient based on who sent the message
        if request.user.pk == vision_request.creator.user.pk:
            # Creator sent message, notify requester
            recipient = vision_request.requester
            sender_name = vision_request.creator.user.username
        elif request.user == vision_request.requester:
            # Requester sent message, notify creator
            recipient = vision_request.creator.user
            sender_name = vision_request.requester.username
        else:
            return Response({
                'error': 'You are not a participant in this chat'
            }, status=HTTPStatus.FORBIDDEN)

        # Create activity and send notification
        ActivityManager.create_activity_and_notify(
            actor=request.user,
            action_type='chat',
            target_id=request_id,
            target_type='vision_request',
            notify_user=recipient,
            notification_title="New Chat Message",
            notification_body=f"{sender_name}: {message[:50]}..." if len(message) > 50 else f"{sender_name}: {message}",
            data={
                'request_id': str(request_id),
                'type': 'chat_message',
                'sender_id': str(request.user.id),
                'sender_name': sender_name
            }
        )

        return Response({
            'message': 'Notification sent successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error sending chat notification: {e}")
        return Response({
            'error': 'An error occurred while sending the notification'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def stream_violation(request):
    """
    Handle stream content violations and send email notifications to admins.
    Expected POST data:
    - api_key: API key for authentication
    - stream_key: The key of the stream that violated content policy
    - violation_type: Type of violation detected
    - confidence: Confidence score of the violation
    - timestamp: When the violation occurred
    - image_url: URL of the captured frame (optional)
    """
    try:
        # Verify API key
        api_key = request.data.get('api_key')
        if api_key != settings.NGINX_API_KEY:
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        # Get violation details
        stream_key = request.data.get('stream_key')
        violation_type = request.data.get('violation_type', 'Unknown')
        confidence = request.data.get('confidence', 0)
        timestamp = request.data.get('timestamp')
        image_url = request.data.get('image_url', 'Not provided')

        # Find the vision/stream
        try:
            vision = Vision.objects.select_related('creator', 'creator__user').get(stream_key=stream_key)
        except Vision.DoesNotExist:
            return Response({"error": "Stream not found"}, status=HTTPStatus.NOT_FOUND)

        # Prepare email content
        SENDER = f"POV Stream Moderation <{settings.SES_FROM_EMAIL}>"
        RECIPIENT = settings.ADMIN_EMAIL
        SUBJECT = f"Stream Content Violation Detected - {vision.title}"
        
        BODY_TEXT = f"""
        Content Violation Detected

        Stream: {vision.title}
        Creator: {vision.creator.user.username}
        Violation Type: {violation_type}
        Confidence: {confidence}%
        Timestamp: {timestamp}
        Stream Key: {stream_key}
        Captured Frame: {image_url}

        This stream has been automatically terminated due to content policy violations.
        """

        BODY_HTML = f"""
        <html>
        <head></head>
        <body>
            <h2>Content Violation Detected</h2>
            <p><strong>Stream:</strong> {vision.title}</p>
            <p><strong>Creator:</strong> {vision.creator.user.username}</p>
            <p><strong>Violation Type:</strong> {violation_type}</p>
            <p><strong>Confidence:</strong> {confidence}%</p>
            <p><strong>Timestamp:</strong> {timestamp}</p>
            <p><strong>Stream Key:</strong> {stream_key}</p>
            <p><strong>Captured Frame:</strong> <a href="{image_url}">{image_url}</a></p>
            <p>This stream has been automatically terminated due to content policy violations.</p>
        </body>
        </html>
        """

        # Create SES client
        ses_client = boto3.client(
            'ses',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )

        try:
            response = ses_client.send_email(
                Destination={
                    'ToAddresses': [RECIPIENT],
                },
                Message={
                    'Body': {
                        'Html': {
                            'Charset': 'UTF-8',
                            'Data': BODY_HTML,
                        },
                        'Text': {
                            'Charset': 'UTF-8',
                            'Data': BODY_TEXT,
                        },
                    },
                    'Subject': {
                        'Charset': 'UTF-8',
                        'Data': SUBJECT,
                    },
                },
                Source=SENDER
            )
        except ClientError as e:
            logger.error(f"Failed to send email notification: {e.response['Error']['Message']}")
            # Continue execution even if email fails
        
        # Log the violation
        logger.warning(
            f"Content violation detected - Stream: {vision.title}, "
            f"Creator: {vision.creator.user.username}, Type: {violation_type}, "
            f"Confidence: {confidence}%"
        )

        return Response({
            "message": "Violation reported and notification sent",
            "stream_key": stream_key,
            "violation_type": violation_type
        })

    except Exception as e:
        logger.error(f"Error handling stream violation: {e}")
        return Response(
            {'error': f'Error handling stream violation: {str(e)}'},
            status=HTTPStatus.INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def terminate_stream(request):
    """
    Terminate a live stream and update its status to failed.
    Expected POST data:
    - api_key: API key for authentication
    - stream_key: The key of the stream to terminate
    - reason: Reason for termination
    """
    try:
        # Verify API key
        api_key = request.data.get('api_key')
        if api_key != settings.NGINX_API_KEY:
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        # Get stream key and reason
        stream_key = request.data.get('stream_key')
        reason = request.data.get('reason', 'Unknown')

        if not stream_key:
            return Response({"error": "Stream key is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Parse username and vision_id from stream key (format: username-vision_id)
        try:
            username, vision_id = stream_key.rsplit('-', 1)
            vision_id = int(vision_id)
        except (ValueError, AttributeError):
            return Response({"error": "Invalid stream key format"}, status=status.HTTP_400_BAD_REQUEST)

        # Find the vision
        try:
            vision = Vision.objects.select_related('creator', 'creator__user').get(
                pk=vision_id,
                creator__user__username=username
            )
        except Vision.DoesNotExist:
            return Response({"error": "Stream not found"}, status=HTTPStatus.NOT_FOUND)

        # Update vision status to failed
        vision.status = 'failed'
        vision.live = False
        vision.save()

        # Log the termination
        logger.warning(
            f"Stream terminated - Vision: {vision.title}, "
            f"Creator: {vision.creator.user.username}, "
            f"Reason: {reason}"
        )

        # Notify the creator
        try:
            send_fcm_notification(
                vision.creator.user,
                "Stream Terminated",
                f"Your stream '{vision.title}' has been terminated due to {reason}",
                data={
                    'vision_id': str(vision.id),
                    'status': 'failed',
                    'reason': reason
                }
            )
        except Exception as e:
            logger.error(f"Failed to send termination notification: {e}")

        return Response({
            "message": "Stream terminated successfully",
            "vision_id": vision.id,
            "status": vision.status
        })

    except Exception as e:
        logger.error(f"Error terminating stream: {e}")
        return Response(
            {'error': f'Error terminating stream: {str(e)}'},
            status=HTTPStatus.INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def get_creator_live_visions(request, creator_pk):
    """
    Get all currently live visions for a specific creator
    """
    try:
        # Get creator
        try:
            creator = Creator.objects.get(pk=creator_pk)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Get all visions where creator matches and live is True
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            creator=creator,
            live=True,
            status='live'
        ).select_related(
            'creator',
            'creator__user'
        ).prefetch_related(
            'interests'
        ).order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)

        # Serialize the results
        serializer = VisionSerializer(results, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error getting creator live visions: {e}")
        return Response({
            'error': 'An error occurred while getting live visions'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def purchase_pay_per_view(request, vision_pk):
    """
    Purchase access to a pay-per-view vision using credits
    """
    try:
        # Get the vision
        try:
            vision = Vision.objects.get(pk=vision_pk)
        except Vision.DoesNotExist:
            return Response({
                'error': 'Vision not found'
            }, status=HTTPStatus.NOT_FOUND)

        # Verify vision is PPV
        if vision.access_type != 'premium':
            return Response({
                'error': 'This vision is not pay-per-view'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user and spectator
        user = User.objects.get(pk=request.user.pk)
        spectator = Spectator.objects.get(user=user)

        # Check if already purchased
        if vision in spectator.ppv_visions.all():
            return Response({
                'error': 'You have already purchased this vision'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user's credit balance
        try:
            spectator_credit_balance = CreditBalance.objects.get(user=user)
        except CreditBalance.DoesNotExist:
            return Response({
                'error': 'No credit balance found for spectator'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get creator's credit balance
        try:
            creator_user = vision.creator.user
            creator_credit_balance = CreditBalance.objects.get(user=creator_user)
        except CreditBalance.DoesNotExist:
            # Create balance for creator if it doesn't exist
            creator_credit_balance = CreditBalance.objects.create(
                user=creator_user,
                spectator_balance=0,
                creator_balance=0
            )

        # Check if user has enough credits
        if spectator_credit_balance.spectator_balance < vision.ppv_price:
            return Response({
                'error': 'Insufficient credits',
                'required_credits': vision.ppv_price,
                'current_balance': spectator_credit_balance.spectator_balance
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create transaction and transfer credits
        with transaction.atomic():
            # Deduct credits from spectator's balance
            spectator_credit_balance.deduct_spectator_credits(vision.ppv_price)

            # Add credits to creator's balance
            creator_credit_balance.add_creator_credits(vision.ppv_price)

            # Create credit transaction record for spectator (debit)
            CreditTransaction.objects.create(
                user=user,
                amount=-vision.ppv_price,
                transaction_type='one_time_purchase',
                metadata={
                    'vision_id': vision.id,
                    'vision_title': vision.title,
                    'creator_id': vision.creator.user.id,
                    'creator_username': vision.creator.user.username,
                    'transaction_description': 'Pay-per-view purchase'
                }
            )
            
            # Create credit transaction record for creator (credit)
            CreditTransaction.objects.create(
                user=creator_user,
                amount=vision.ppv_price,
                transaction_type='one_time_purchase',
                metadata={
                    'vision_id': vision.id,
                    'vision_title': vision.title,
                    'spectator_id': user.id,
                    'spectator_username': user.username,
                    'transaction_description': 'Pay-per-view revenue'
                }
            )

            # Add vision to user's purchased PPV collection
            spectator.ppv_visions.add(vision)
            spectator.save()

            # Create activity event
            ActivityManager.create_activity_event(
                actor=user,
                action_type='purchase',
                target_id=vision.id,
                target_type='vision'
            )

        return Response({
            'message': 'Vision purchased successfully',
            'remaining_balance': spectator_credit_balance.spectator_balance,
            'vision': VisionSerializer(vision, context={'request': request}).data
        }, status=status.HTTP_200_OK)

    except ValueError as e:
        logger.error(f"Credit balance error: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error purchasing pay-per-view vision: {e}")
        return Response({
            'error': 'An error occurred while processing the purchase'
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_ppv_visions(request):
    """
    Get paginated list of purchased pay-per-view visions for the authenticated user
    """
    
    try:
        # Get user's spectator profile
        spectator = Spectator.objects.get(user=request.user)
        
        # Get all purchased PPV visions
        visions = spectator.ppv_visions.all().select_related(
            'creator',
            'creator__user'
        ).prefetch_related(
            'interests'
        ).order_by('-created_at')

        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        results = paginator.paginate_queryset(visions, request)

        # Serialize the results
        serializer = VisionSerializer(results, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    except Spectator.DoesNotExist:
        return Response({
            'error': 'Spectator profile not found',
            'message': 'Please create a spectator profile to view your purchased pay-per-view visions'
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        logger.error(f"Error fetching PPV visions: {e}")
        return Response({
            'message': 'An error occurred while fetching PPV visions',
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

def get_similar_visions_fast(vision_id, num_results=10):
    """
    Get similar visions quickly using the Annoy ANN index from database or cache.
    Much faster than database lookups for large datasets and more persistent.
    """
    try:
        # Try to get the index from cache first (fastest)
        cached_index_data = cache.get(f"{CACHE_PREFIX}ann_index")
        
        # If not in cache, try to get from database
        if not cached_index_data:
            from videos.models import AnnoyIndex as AnnoyIndexModel
            try:
                db_index = AnnoyIndexModel.objects.filter(is_current=True).latest('created_at')
                
                # Convert memoryview to bytes before caching
                index_binary = bytes(db_index.index_binary)
                
                # Create the cache data and store it for next time
                cached_index_data = {
                    'index_binary': index_binary,  # Now it's bytes, not memoryview
                    'vision_ids': db_index.vision_ids,
                    'vector_size': db_index.vector_size,
                    'last_update': db_index.created_at.isoformat(),
                    'vision_count': len(db_index.vision_ids)
                }
                cache.set(f"{CACHE_PREFIX}ann_index", cached_index_data, CACHE_TIMEOUT * 12)
                
                logger.info("Loaded ANN index from database to cache")
            except AnnoyIndexModel.DoesNotExist:
                logger.info("ANN index not found in database. Falling back to similarity table.")
                # Fallback to database similarity table
                return list(VisionSimilarity.objects.filter(
                    vision_id=vision_id
                ).order_by('-final_score')[:num_results].values_list(
                    'similar_vision_id', 'final_score'
                ))
        
        # Rest of the function remains the same - use the cached_index_data
        # Get the vision IDs and vector size
        vision_ids = cached_index_data['vision_ids']
        vector_size = cached_index_data['vector_size']
        
        # Create mappings
        vision_to_idx = {vid: idx for idx, vid in enumerate(vision_ids)}
        
        # If vision is in our index
        if vision_id in vision_to_idx:
            # Write the binary data to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(cached_index_data['index_binary'])
            temp_file.close()
            
            # Load the Annoy index
            index = AnnoyIndex(vector_size, 'angular')
            index.load(temp_file.name)
            
            # Get the vision index
            vision_idx = vision_to_idx[vision_id]
            
            # Query for nearest neighbors
            similar_idxs, distances = index.get_nns_by_item(vision_idx, num_results+1, 
                                                          include_distances=True)
            
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            # Convert results to vision IDs and scores
            similar_visions = []
            for idx, distance in zip(similar_idxs, distances):
                if idx != vision_idx and idx < len(vision_ids):  # Skip self and validate index
                    # Convert angular distance to similarity score (1.0 is most similar)
                    similarity = 1.0 - (distance / 2.0)  # Annoy angular distance ranges 0-2
                    similar_visions.append((vision_ids[idx], similarity))
            
            return similar_visions[:num_results]
        
        # Vision not in index, fall back to database
        return list(VisionSimilarity.objects.filter(
            vision_id=vision_id
        ).order_by('-final_score')[:num_results].values_list(
            'similar_vision_id', 'final_score'
        ))
        
    except Exception as e:
        logger.error(f"Error retrieving similar visions using Annoy: {e}")
        # Fallback to database
        return list(VisionSimilarity.objects.filter(
            vision_id=vision_id
        ).order_by('-final_score')[:num_results].values_list(
            'similar_vision_id', 'final_score'
        ))

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_top_povs(request, creator_pk):
    """
    Get top performing POVs (visions) for a creator based on engagement metrics.
    Engagement is calculated as a weighted combination of views, likes, and comments.
    """
    try:
        # Check if we're looking at our own profile or someone else's
        is_own_profile = False
        if hasattr(request.user, 'creator') and request.user.creator.pk == creator_pk:
            is_own_profile = True
        elif request.user.is_staff:  # Staff can see anyone's stats
            is_own_profile = True
            
        # Get query parameters for customization
        time_period = request.GET.get('time_period', 'all')  # 'week', 'month', 'year', 'all'
        limit = int(request.GET.get('limit', 10))  # Number of top POVs to return
        
        # Get the creator
        try:
            creator = Creator.objects.get(pk=creator_pk)
        except Creator.DoesNotExist:
            return Response({
                'error': 'Creator not found'
            }, status=HTTPStatus.NOT_FOUND)
            
        # Build base queryset
        visions = Vision.with_locks.with_is_locked(request.user).filter(
            creator=creator,
            status='vod'  # Only completed visions, not drafts or failed uploads
        )
        
        # Apply time period filter if specified
        if time_period == 'week':
            visions = visions.filter(created_at__gte=timezone.now() - timedelta(days=7))
        elif time_period == 'month':
            visions = visions.filter(created_at__gte=timezone.now() - timedelta(days=30))
        elif time_period == 'year':
            visions = visions.filter(created_at__gte=timezone.now() - timedelta(days=365))
        
        # Calculate engagement score as a weighted combination of metrics
        # Higher weights for more valuable engagement types
        visions = visions.order_by('-engagement_score')  # Sort by highest engagement score
        
        # If it's the creator viewing their own top POVs or an admin,
        # we'll include some additional metrics for analytics
        if is_own_profile:
            visions = visions.annotate(
                engagement_rate=ExpressionWrapper(
                    (F('likes') + F('comment_count')) * 100.0 / Greatest(F('views'), Value(1)),
                    output_field=FloatField()
                ),
                days_since_created=ExpressionWrapper(
                    Extract(timezone.now() - F('created_at'), 'day'),
                    output_field=IntegerField()
                )
            )
        
        # Set up pagination
        paginator = PageNumberPagination()
        paginator.page_size = min(limit, 50)  # Cap at 50 to prevent excessive load
        results = paginator.paginate_queryset(visions, request)
        
        # Serialize the results - efficient serialization with needed fields only
        serializer = VisionSerializer(
            results, 
            many=True, 
            context={'request': request}
        )
        
        # Return paginated response
        return paginator.get_paginated_response(serializer.data)
    
    except Exception as e:
        logger.error(f"Error getting top POVs for creator: {e}")
        return Response({
            'error': 'An error occurred while fetching top POVs',
            'message': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_vision(request, vision_pk):
    try:
        # Get the vision
        vision = Vision.objects.get(pk=vision_pk)
        
        # Check if the user is the creator of the vision
        if request.user.pk != vision.creator.user.pk:
            return Response({
                'error': 'You do not have permission to delete this vision.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Store the title for the response message
        vision_title = vision.title
        
        # Delete the vision
        vision.delete()
        
        return Response({
            'message': f'Vision "{vision_title}" deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except Vision.DoesNotExist:
        return Response({
            'error': 'Vision not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error deleting vision: {e}")
        return Response({
            'error': 'An error occurred while deleting the vision'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def delete_comment(request, comment_pk):
    try:
        # Get the comment
        comment = Comment.objects.get(pk=comment_pk)
        
        # Check if the user is the comment author or the vision creator
        if request.user != comment.user and (not comment.vision.creator or request.user != comment.vision.creator.user):
            return Response({
                'error': 'You do not have permission to delete this comment'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # If this is a parent comment, also delete all replies
        if comment.parent_comment is None:
            # Note: This will automatically be handled by the database due to CASCADE
            # But we may want to include additional logic for related entities in the future
            pass
            
        # Store the comment ID for response
        comment_id = comment.pk
        vision_id = comment.vision.pk
        
        # Delete the comment
        comment.delete()
        
        # Update the denormalized comment count on the related vision
        if comment.parent_comment is None:  # Only decrement for parent comments
            Vision.objects.filter(pk=vision_id).update(comment_count=models.F('comment_count') - 1)
        
        return Response({
            'message': 'Comment deleted successfully',
            'comment_id': comment_id,
            'vision_id': vision_id
        }, status=status.HTTP_200_OK)
        
    except Comment.DoesNotExist:
        return Response({
            'error': 'Comment not found'
        }, status=status.HTTP_404_NOT_FOUND)
        
    except Exception as e:
        logger.error(f"Error deleting comment: {e}")
        return Response({
            'error': 'An error occurred while deleting the comment'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

