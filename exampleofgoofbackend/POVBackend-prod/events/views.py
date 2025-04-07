from datetime import datetime, timedelta
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from http import HTTPStatus
import cloudinary.uploader
from pov_backend import settings
from .models import Event, EventSimilarity
from .serializers import EventSerializer
from videos.models import Vision
from users.models import Creator, Interest, Spectator
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from django.utils import timezone
from .models import Event, Spectator
from django.db.models import Count, Q, Case, When, BooleanField, FloatField, ExpressionWrapper, F, IntegerField, Value, Subquery, OuterRef
from django.db.models.functions import Cast, Now, Extract, Coalesce, Random
from rest_framework.authentication import TokenAuthentication
from django.utils.dateparse import parse_datetime
import logging
import random
from django.core.cache import cache
from django.db.models import F, Case, When, Value, FloatField, Count, Q, ExpressionWrapper
from django.db.models.functions import Extract, Greatest
import os
import tempfile
from annoy import AnnoyIndex

logger = logging.getLogger(__name__)

# Event similarity cache constants
EVENT_CACHE_PREFIX = "event_similarity_"
EVENT_CACHE_TIMEOUT = 60 * 60  # 1 hour

@api_view(['GET', 'POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_create_delete_events(request):
    if request.method == 'GET':
        try:
            events = Event.objects.all()
            serialized_events = EventSerializer(events, many=True, context={'user': request.user})
            return Response({'message': 'Successfully retrieved events', 'data': serialized_events.data}, status=HTTPStatus.OK)
        except Exception as e:
            logger.error(f"Error retrieving events: {str(e)}")
            return Response({'message': 'There was an error', 'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    elif request.method == 'POST':
        try:
            creator = Creator.objects.get(user=request.user)
            title = request.data.get('title')
            description = request.data.get('description')
            start_time_str = request.data.get('start_time')
            thumbnail = request.FILES.get('thumbnail', None)
            camera_type = request.data.get('camera_type')
            quality = request.data.get('quality')
            stereo_mapping = request.data.get('stereo_mapping')
            aspect_ratio = request.data.get('aspect_ratio')

            logger.info(f"Creating event for creator {creator.user.username} with title: {title}")

            if not title or not description or not start_time_str:
                logger.warning("Missing required fields in event creation")
                return Response({'message': 'Title, description, and start time are required'}, status=HTTPStatus.BAD_REQUEST)
            
            if not thumbnail:
                logger.warning("No thumbnail provided for event creation")
                return Response({'message': 'Bad request: Thumbnail is required'}, status=HTTPStatus.BAD_REQUEST)
            
            # Parse the start_time string into a datetime object and ensure it's timezone-aware
            start_time = parse_datetime(start_time_str)
            if not start_time:
                logger.warning(f"Invalid start time format provided: {start_time_str}")
                return Response({'message': 'Invalid start time format. Use ISO format (e.g. 2023-05-01T12:00:00Z)'}, status=HTTPStatus.BAD_REQUEST)
            
            # Ensure start_time is timezone-aware
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)

            event = Event.objects.create(
                creator=creator,
                title=title,
                description=description,
                start_time=start_time
            )
            
            logger.info(f"Created event with ID: {event.pk}")
            
            event.remind_me_list.add(Spectator.objects.get(pk=request.user.pk))

            vision = Vision.objects.create(
                title=event.title,
                thumbnail='placeholder',  # Will be updated after upload
                creator=creator,
                description=event.description,
                status='pending_live',
                camera_type=camera_type,
                quality=quality,
                stereo_mapping=stereo_mapping,
                aspect_ratio=aspect_ratio
            )
            
            logger.info(f"Created vision with ID: {vision.pk}")

            try:
                # Upload thumbnail to Cloudinary
                logger.info(f"Uploading thumbnail for event {event.pk}")
                thumbnail_res = cloudinary.uploader.upload(
                    thumbnail,
                    public_id=f'{request.user.username}-{vision.pk}-thumbnail',
                    unique_filename=False,
                    overwrite=True
                )
                vision.thumbnail = thumbnail_res['secure_url']
                event.thumbnail = thumbnail_res['secure_url']  # Also save thumbnail URL to event
                vision.save()
                event.save()
                logger.info(f"Successfully uploaded thumbnail for event {event.pk}: {thumbnail_res['secure_url']}")
            except Exception as e:
                logger.error(f"Error uploading thumbnail for event {event.pk}: {str(e)}")
                event.delete()  # Cleanup if thumbnail upload fails
                vision.delete()
                return Response({'message': 'Error uploading thumbnail', 'error': str(e)}, status=HTTPStatus.BAD_REQUEST)

            # Add interests if provided
            interests = request.data.get('interests', [])
            if isinstance(interests, str):
                interests = [i.strip() for i in interests.split(',') if i.strip()]
            logger.info(f"Adding {len(interests)} interests to vision {vision.pk}")
            for interest_item in interests:
                if interest_item.isdigit():
                    try:
                        interest = Interest.objects.get(pk=int(interest_item))
                    except Interest.DoesNotExist:
                        interest, created = Interest.objects.get_or_create(name=interest_item)
                else:
                    interest, created = Interest.objects.get_or_create(name=interest_item)
                vision.interests.add(interest)

            event.vision = vision
            event.save()
            
            logger.info(f"Successfully created event {event.pk} with vision {vision.pk}")
            return Response({
                'message': 'Successfully created event', 
                'data': EventSerializer(event, context={'user': request.user}).data, 
                'id': vision.pk
            }, status=HTTPStatus.CREATED)
        except Creator.DoesNotExist:
            logger.error(f"Creator not found for user {request.user.pk}")
            return Response({'message': 'Creator not found'}, status=HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.error(f"Error creating event: {str(e)}")
            return Response({'message': 'There was an error', 'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def edit_or_delete_events(request, pk):
    if request.method == 'PUT':
        try:
            event = Event.objects.get(pk=pk)
            logger.info(f"Updating event {pk} for user {request.user.username}")
            
            # Verify the user is the creator
            if event.creator.user != request.user:
                logger.warning(f"Unauthorized attempt to update event {pk} by user {request.user.username}")
                return Response({'message': 'Unauthorized'}, status=HTTPStatus.UNAUTHORIZED)
            
            # Update event fields directly
            event.title = request.data.get('title', event.title)
            event.description = request.data.get('description', event.description)
            start_time_str = request.data.get('start_time')
            if start_time_str:
                start_time = parse_datetime(start_time_str)
                if not start_time:
                    logger.warning(f"Invalid start time format provided: {start_time_str}")
                    return Response({'message': 'Invalid start time format. Use ISO format (e.g. 2023-05-01T12:00:00Z)'}, status=HTTPStatus.BAD_REQUEST)
                
                # Ensure start_time is timezone-aware
                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                event.start_time = start_time
            
            event.save()
            logger.info(f"Updated event {pk} basic details")
            
            # Update associated vision if it exists
            if event.vision:
                vision = event.vision
                vision.title = event.title
                vision.description = event.description
                
                # Handle thumbnail update if provided
                thumbnail = request.FILES.get('thumbnail')
                if thumbnail:
                    try:
                        logger.info(f"Uploading new thumbnail for event {pk}")
                        thumbnail_res = cloudinary.uploader.upload(
                            thumbnail,
                            public_id=f'{request.user.username}-{vision.pk}-thumbnail',
                            unique_filename=False,
                            overwrite=True
                        )
                        vision.thumbnail = thumbnail_res['secure_url']
                        event.thumbnail = thumbnail_res['secure_url']  # Also update event thumbnail
                        logger.info(f"Successfully uploaded new thumbnail for event {pk}: {thumbnail_res['secure_url']}")
                    except Exception as e:
                        logger.error(f"Error uploading thumbnail for event {pk}: {str(e)}")
                        return Response({'message': 'Error uploading thumbnail', 'error': str(e)}, status=HTTPStatus.BAD_REQUEST)
                    
                # Update interests if provided
                if 'interests' in request.data:
                    logger.info(f"Updating interests for event {pk}")
                    vision.interests.clear()
                    for interest_pk in request.data['interests']:
                        try:
                            interest = Interest.objects.get(pk=interest_pk)
                            vision.interests.add(interest)
                        except Interest.DoesNotExist:
                            logger.warning(f"Interest with id {interest_pk} not found")
                            return Response({'message': f'Interest with id {interest_pk} not found'}, status=HTTPStatus.NOT_FOUND)
                        
                vision.save()
                event.save()
                logger.info(f"Successfully updated event {pk} and associated vision {vision.pk}")
            
            return Response({
                'message': 'Successfully updated event',
                'data': EventSerializer(event, context={'user': request.user}).data
            }, status=HTTPStatus.OK)
                
        except Event.DoesNotExist:
            logger.error(f"Event {pk} not found")
            return Response({
                'message': 'Event not found',
                'error': True
            }, status=HTTPStatus.NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating event {pk}: {str(e)}")
            return Response({
                'message': 'There was an error',
                'error': str(e)
            }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
    elif request.method == 'DELETE':
        try:
            event = Event.objects.get(pk=pk)
            logger.info(f"Deleting event {pk}")
            event.delete()
            logger.info(f"Successfully deleted event {pk}")
            return Response({'message': 'Successfully deleted event'}, status=HTTPStatus.OK)
        except Exception as e:
            logger.error(f"Error deleting event {pk}: {str(e)}")
            return Response({'message': 'There was an error', 'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def activate_event_livestream(request, pk):
    try:
        event = Event.objects.get(pk=pk)
        print(event)
        vision_obj = event.vision

        if vision_obj:
            # Make vision live without URL modifications
            vision_obj.creator = Creator.objects.get(user=request.user)
            vision_obj.live = True
            vision_obj.status = 'live'

            rtmp_stream_key = f"{request.user.username}-{vision_obj.pk}"
            vision_obj.rtmp_stream_key = rtmp_stream_key
            vision_obj.url = f"{settings.FILE_HOST}/{rtmp_stream_key}.m3u8"
            vision_obj.save()

            # Update event with updated vision
            event.vision = vision_obj
            event.save()

            return Response({
                'message': 'Successfully activated event livestream',
                'vision_id': vision_obj.pk,
                'rtmp_stream_key': rtmp_stream_key
            }, status=HTTPStatus.OK)
        else:
            return Response({'message': 'Invalid vision data'}, status=HTTPStatus.BAD_REQUEST)
    except Event.DoesNotExist:
        return Response({'message': 'Event not found', 'error': True}, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({'message': 'There was an error', 'error': str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_event_by_creator(request, pk):
    try:
        creator = Creator.objects.get(pk=pk)
        events = Event.objects.filter(creator=creator).order_by('start_time')
        return Response({'message': 'Successfully retrieved events', 'data': EventSerializer(events, many=True, context={'user': request.user}).data})
    except Exception as e:
        return Response({'message': 'There was an error', 'error': True}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_upcoming_events_by_interests(request):
    try:
        interests = request.GET.getlist('interests')
        q_interests = [Interest.objects.get(name=interest_name) for interest_name in interests]
        events = Event.objects.annotate(num_waiting=Count('remind_me_list')).filter(vision__interests__in=q_interests).filter(start_time__gte=timezone.now()).distinct().order_by('-num_waiting', 'start_time')
        return Response({'message': 'Successfully retrieved events', 'data': EventSerializer(events, many=True, context={'user': request.user}).data})
    except Exception as e:
        return Response({'message': 'There was an error', 'error': True}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def add_or_remove_from_remind_me_list(request, event_pk):
    try:
        spectator = Spectator.objects.get(user=request.user)
        event = Event.objects.get(pk=event_pk)
        if spectator in event.remind_me_list.all():
            event.remind_me_list.remove(spectator)
            return Response({'message': 'Spectator successfully removed from remind me list'}, status=HTTPStatus.OK)
        else:
            event.remind_me_list.add(spectator)
            event.save()
            return Response({'message': 'Spectator successfully added to remind me list'}, status=HTTPStatus.OK)
    except Exception as e:
        return Response({'message': 'There was an error', 'error': True}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_events_from_subscriptions(request):
    try:
        spectator = Spectator.objects.get(user=request.user)
        events = Event.objects.annotate(num_waiting=Count('remind_me_list')).filter(creator__in=spectator.subscriptions.all()).filter(start_time__gte=timezone.now()).distinct().order_by('-num_waiting')
        return Response({'message': 'Successfully retrieved events', 'data': EventSerializer(events, many=True, context={'user': request.user}).data}, status=HTTPStatus.OK)
    except Exception as e:
        return Response({'message': 'There was an error', 'error': True}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

def get_similar_events_fast(event_id, num_results=10):
    """
    Get similar events quickly using the Annoy ANN index from database or cache.
    Much faster than database lookups for large datasets.
    """
    try:
        # Try to get the index from cache first (fastest)
        cached_index_data = cache.get(f"{EVENT_CACHE_PREFIX}ann_index")
        
        # If not in cache, try to get from database
        if not cached_index_data:
            from events.models import EventAnnoyIndex
            try:
                db_index = EventAnnoyIndex.objects.filter(is_current=True).latest('created_at')
                
                # Convert memoryview to bytes before caching
                index_binary = bytes(db_index.index_binary)
                
                # Create the cache data and store it for next time
                cached_index_data = {
                    'index_binary': index_binary,
                    'event_ids': db_index.event_ids,
                    'vector_size': db_index.vector_size,
                    'last_update': db_index.created_at.isoformat(),
                    'event_count': len(db_index.event_ids)
                }
                cache.set(f"{EVENT_CACHE_PREFIX}ann_index", cached_index_data, EVENT_CACHE_TIMEOUT)
                
                logger.info("Loaded Event ANN index from database to cache")
            except EventAnnoyIndex.DoesNotExist:
                logger.info("Event ANN index not found in database. Falling back to similarity table.")
                # Fallback to database similarity table
                return list(EventSimilarity.objects.filter(
                    event_id=event_id
                ).order_by('-final_score')[:num_results].values_list(
                    'similar_event_id', 'final_score'
                ))
        
        # Use the cached_index_data
        # Get the event IDs and vector size
        event_ids = cached_index_data['event_ids']
        vector_size = cached_index_data['vector_size']
        
        # Create mappings
        event_to_idx = {int(eid): idx for idx, eid in enumerate(event_ids)}
        
        # If event is in our index
        if int(event_id) in event_to_idx:
            # Write the binary data to a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(cached_index_data['index_binary'])
            temp_file.close()
            
            # Load the Annoy index
            index = AnnoyIndex(vector_size, 'angular')
            index.load(temp_file.name)
            
            # Get the event index
            event_idx = event_to_idx[int(event_id)]
            
            # Query for nearest neighbors
            similar_idxs, distances = index.get_nns_by_item(event_idx, num_results+1, 
                                                          include_distances=True)
            
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            # Convert results to event IDs and scores
            similar_events = []
            for idx, distance in zip(similar_idxs, distances):
                if idx != event_idx and idx < len(event_ids):  # Skip self and validate index
                    # Convert angular distance to similarity score (1.0 is most similar)
                    similarity = 1.0 - (distance / 2.0)  # Annoy angular distance ranges 0-2
                    similar_events.append((int(event_ids[idx]), similarity))
            
            return similar_events[:num_results]
        
        # Event not in index, fall back to database
        return list(EventSimilarity.objects.filter(
            event_id=event_id
        ).order_by('-final_score')[:num_results].values_list(
            'similar_event_id', 'final_score'
        ))
        
    except Exception as e:
        logger.error(f"Error retrieving similar events using Annoy: {e}")
        # Fallback to database
        return list(EventSimilarity.objects.filter(
            event_id=event_id
        ).order_by('-final_score')[:num_results].values_list(
            'similar_event_id', 'final_score'
        ))

def get_recommended_events_algorithm(user, interest=None):
    """
    Hybrid recommendation algorithm for events combining similarity data,
    user preferences, and engagement metrics with diversity controls
    """
    try:
        # Efficient caching
        cache_key = f"user_recommended_events_{user.id}_{interest}"
        cached_results = cache.get(cache_key)
        # Uncomment to enable caching
        # if cached_results:
        #     return cached_results
            
        # Get user data
        try:
            spectator = Spectator.objects.filter(user=user).prefetch_related(
                'interests', 'subscriptions'
            ).first()
            
            if not spectator:
                # Cold start: Return trending events
                return get_trending_events(user, interest)
                
            # Extract user preferences
            user_data = {
                'interest_ids': list(spectator.interests.values_list('pk', flat=True)),
                'subscribed_creator_ids': list(spectator.subscriptions.values_list('pk', flat=True)),
                'remind_me_event_ids': list(Event.objects.filter(remind_me_list=spectator).values_list('pk', flat=True))
            }
        except Exception as e:
            logger.error(f"Error fetching user data: {e}")
            user_data = {'interest_ids': [], 'subscribed_creator_ids': [], 'remind_me_event_ids': []}
            
        # Current time for time-based scoring
        current_time = timezone.now()
        
        # 1. Get base queryset with annotations
        base_queryset = Event.objects.select_related(
            'creator', 'creator__user', 'vision'
        ).prefetch_related(
            'vision__interests',
            'remind_me_list'
        )

        # Apply interest filter if specified
        if interest:
            base_queryset = base_queryset.filter(vision__interests__name=interest).distinct()
        
        # 2. Separate upcoming and live events
        # We want to prioritize differently based on event timing
        upcoming_events = base_queryset.filter(start_time__gt=current_time).annotate(
            days_until=Extract(F('start_time') - current_time, 'day') + 1,
            remind_me_count=Count('remind_me_list', distinct=True),
            is_subscribed=Case(
                When(creator_id__in=user_data['subscribed_creator_ids'], then=True),
                default=False,
                output_field=BooleanField()
            ),
            interest_match_count=Count(
                'vision__interests',
                filter=Q(vision__interests__pk__in=user_data['interest_ids']),
                distinct=True
            )
        )
        
        live_events = base_queryset.filter(
            start_time__lte=current_time,
            vision__status='live'
        ).annotate(
            remind_me_count=Count('remind_me_list', distinct=True),
            is_subscribed=Case(
                When(creator_id__in=user_data['subscribed_creator_ids'], then=True),
                default=False,
                output_field=BooleanField()
            ),
            interest_match_count=Count(
                'vision__interests', 
                filter=Q(vision__interests__pk__in=user_data['interest_ids']),
                distinct=True
            )
        )
        
        # 3. Score events and compile final results
        # First for upcoming events
        upcoming_scored = []
        for event in upcoming_events:
            # Time relevance - events closer to now are more relevant
            time_score = min(10.0, 10.0 / event.days_until) if event.days_until else 1.0
            
            # Subscription boost
            subscription_boost = 3.0 if event.is_subscribed else 0.0
            
            # Interest match
            interest_boost = event.interest_match_count * 2.0
            
            # Remind me count (popularity)
            popularity_score = min(5.0, event.remind_me_count / 5.0)
            
            # Already in remind me list
            in_list_boost = 1.5 if event.pk in user_data['remind_me_event_ids'] else 0.0
            
            # Get similarity boost from remind_me events
            similarity_score = 0.0
            for remind_event_id in user_data['remind_me_event_ids'][:5]:  # Use top 5 for efficiency
                for similar_id, score in get_similar_events_fast(remind_event_id, 5):
                    if similar_id == event.pk:
                        similarity_score = max(similarity_score, score * 3.0)  # Boost by similarity
                        
            # Final score calculation
            final_score = (
                time_score +
                subscription_boost +
                interest_boost +
                popularity_score +
                in_list_boost +
                similarity_score
            )
            
            # Add a small random component for diversity
            final_score += random.uniform(0, 0.5)
            
            # Store score
            event.final_score = final_score
            upcoming_scored.append(event)
            
        # Now for live events - prioritize highly
        live_scored = []
        for event in live_events:
            # Live events get a base boost
            live_boost = 5.0
            
            # Subscription boost - higher for live
            subscription_boost = 4.0 if event.is_subscribed else 0.0
            
            # Interest match
            interest_boost = event.interest_match_count * 2.0
            
            # Remind me count (popularity)
            popularity_score = min(6.0, event.remind_me_count / 3.0)
            
            # Already in remind me list
            in_list_boost = 2.0 if event.pk in user_data['remind_me_event_ids'] else 0.0
            
            # Similar to reminded events
            similarity_score = 0.0
            for remind_event_id in user_data['remind_me_event_ids'][:5]:
                for similar_id, score in get_similar_events_fast(remind_event_id, 5):
                    if similar_id == event.pk:
                        similarity_score = max(similarity_score, score * 3.0)
                        
            # Final score calculation
            final_score = (
                live_boost +
                subscription_boost +
                interest_boost +
                popularity_score +
                in_list_boost +
                similarity_score
            )
            
            # Add a small random component for diversity
            final_score += random.uniform(0, 0.3)
            
            # Store score
            event.final_score = final_score
            live_scored.append(event)
            
        # Sort both lists by score
        upcoming_scored.sort(key=lambda x: x.final_score, reverse=True)
        live_scored.sort(key=lambda x: x.final_score, reverse=True)
        
        # 4. Apply diversity controls and create final balanced list
        final_results = []
        
        # Track creators to ensure diversity
        seen_creators = set()
        creator_count = {}
        
        # First, add a few top live events if available (but limit to 3 at start)
        live_added = 0
        for event in live_scored[:3]:
            final_results.append(event)
            
            # Track for diversity
            creator_id = event.creator_id
            seen_creators.add(creator_id)
            creator_count[creator_id] = creator_count.get(creator_id, 0) + 1
            
            live_added += 1
            if live_added >= 3:
                break
        
        # Now start adding upcoming events, making sure we don't have too many from same creator
        upcoming_index = 0
        remaining_slots = 50 - len(final_results)
        
        while len(final_results) < 50 and upcoming_index < len(upcoming_scored):
            event = upcoming_scored[upcoming_index]
            creator_id = event.creator_id
            
            # Skip if we already have too many from this creator, unless we're running low on events
            if creator_count.get(creator_id, 0) >= 3 and len(final_results) < 40:
                upcoming_index += 1
                continue
                
            # Add this event
            final_results.append(event)
            
            # Update creator tracking
            seen_creators.add(creator_id)
            creator_count[creator_id] = creator_count.get(creator_id, 0) + 1
            
            upcoming_index += 1
            
        # Add any remaining live events we haven't added yet (limited to 30% of total)
        live_remaining = live_scored[live_added:]
        max_additional_live = int(0.3 * 50) - live_added
        
        if max_additional_live > 0 and live_remaining:
            # Add remaining live events, respecting creator diversity
            for event in live_remaining:
                if len(final_results) >= 50:
                    break
                    
                creator_id = event.creator_id
                if creator_count.get(creator_id, 0) >= 3:
                    continue
                    
                final_results.append(event)
                creator_count[creator_id] = creator_count.get(creator_id, 0) + 1
                
                max_additional_live -= 1
                if max_additional_live <= 0:
                    break
        
        # Add any remaining upcoming events to fill slots
        for event in upcoming_scored[upcoming_index:]:
            if len(final_results) >= 50:
                break
                
            final_results.append(event)
            
        # Cache results before returning
        cache.set(cache_key, final_results, 60 * 5)  # Cache for 5 minutes
        return final_results
        
    except Exception as e:
        logger.error(f"Error in event recommendation algorithm: {e}", exc_info=True)
        # Just return the list instead of calling get_trending_events
        # to avoid potential loops between functions
        return get_trending_events(user, interest)

def get_trending_events(user, interest=None):
    """
    Get trending events for cold-start situations.
    
    NOTE: This function returns a LIST of Event objects, not a Response object.
    It should always be wrapped in a Response by the calling view function.
    """
    current_time = timezone.now()
    
    # Base query for all upcoming events
    base_query = Event.objects.filter(
        start_time__gt=current_time
    ).annotate(
        days_until=Extract(F('start_time') - current_time, 'day') + 1,
        remind_me_count=Count('remind_me_list')
    )
    
    # Apply interest filter if specified
    if interest:
        base_query = base_query.filter(vision__interests__name=interest).distinct()
    
    # Get trending upcoming events (70%)
    trending = base_query.order_by('-remind_me_count', 'days_until')[:35]
    
    # Get some recent events to mix in (30%)
    recent = base_query.filter(
        ~Q(pk__in=[t.pk for t in trending])
    ).order_by('days_until')[:15]
    
    # Combine results
    results = list(trending) + list(recent)
    return results[:50]

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_recommended_events(request):
    try:
        # Get parameters
        interest = request.GET.get('interest')
        page = int(request.GET.get('page', 1))
        
        # Get a larger batch of recommendations than we need for pagination
        try:
            # This returns a list of Event objects, not a Response
            recommendations = get_recommended_events_algorithm(request.user, interest)
        except Exception as e:
            logger.error(f"Error in recommendation algorithm: {e}")
            # Fallback to trending events but continue with normal processing
            # This also returns a list of Event objects, not a Response
            recommendations = get_trending_events(request.user, interest)
            
        if not isinstance(recommendations, list):
            # Handle case where something unexpected was returned
            logger.error(f"Unexpected type returned from recommendation algorithm: {type(recommendations)}")
            recommendations = []
        
        # Apply pagination
        paginator = PageNumberPagination()
        paginator.page_size = 5
        page_results = paginator.paginate_queryset(recommendations, request)
        
        # Serialize results
        serializer = EventSerializer(page_results, many=True, context={'user': request.user})
        
        # Return paginated response
        return paginator.get_paginated_response(serializer.data)

    except Exception as e:
        logger.error(f"Error in get_recommended_events: {e}")
        return Response({
            'message': 'There was an error getting recommended events', 
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_upcoming_events(request):
    # Get the current user's spectator object
    try:
        spectator = Spectator.objects.get(user=request.user)
    except Spectator.DoesNotExist:
        return Response({"error": "Spectator profile not found"}, status=400)

    # Get the user's interests
    user_interests = spectator.interests.all()

    # Get the creators the user is subscribed to
    subscribed_creators = spectator.subscriptions.all()

    # Get current datetime
    now = timezone.now()

    # Query for upcoming events
    upcoming_events = Event.objects.filter(
        Q(vision__interests__in=user_interests) | Q(creator__in=subscribed_creators),
        start_time__gt=now  # Only future events
    ).annotate(
        is_subscribed_creator=Case(
            When(creator__in=subscribed_creators, then=True),
            default=False,
            output_field=BooleanField()
        )
    ).order_by('-is_subscribed_creator', 'start_time').distinct()

    # Pagination
    paginator = PageNumberPagination()
    paginator.page_size = 10  # You can adjust this number
    paginated_events = paginator.paginate_queryset(upcoming_events, request)

    # Serialize the events
    serializer = EventSerializer(paginated_events, many=True, context={'user': request.user})

    return paginator.get_paginated_response(serializer.data)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_events_by_day(request, creator_pk, date):
    try:
        # Parse the date string to a date object
        target_date = parse_date(date)
        if not target_date:
            return Response({
                'message': 'Invalid date format. Use YYYY-MM-DD',
                'error': True
            }, status=HTTPStatus.BAD_REQUEST)

        # Get the creator
        creator = Creator.objects.get(pk=creator_pk)
        
        # Get all events for this creator on the specified date
        events = Event.objects.filter(
            creator=creator,
            start_time__date=target_date
        ).order_by('start_time')
        
        serialized_events = EventSerializer(events, many=True, context={'user': request.user})
        
        return Response({
            'message': 'Successfully retrieved events',
            'data': serialized_events.data,
            'date': date
        }, status=HTTPStatus.OK)
        
    except Creator.DoesNotExist:
        return Response({
            'message': 'Creator not found',
            'error': True
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        return Response({
            'message': 'There was an error',
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_creator_events_by_month(request, creator_pk, year, month):
    """
    Get all events for a specific creator by month.
    
    Args:
        creator_pk (int): Primary key of the creator
        year (int): Year for which to get events
        month (int): Month for which to get events (1-12)
    """
    try:
        # Validate month
        if not (1 <= month <= 12):
            return Response({
                'error': 'Invalid month. Month must be between 1 and 12'
            }, status=HTTPStatus.BAD_REQUEST)

        # Get the first and last day of the month with timezone awareness
        start_date = timezone.make_aware(timezone.datetime(year, month, 1))
        if month == 12:
            end_date = timezone.make_aware(timezone.datetime(year + 1, 1, 1))
        else:
            end_date = timezone.make_aware(timezone.datetime(year, month + 1, 1))

        print(f"Searching for events between {start_date} and {end_date}")
        print(f"Creator ID: {creator_pk}")

        # Query events for the specified month
        events = Event.objects.filter(
            creator_id=creator_pk,
            start_time__gte=start_date,
            start_time__lt=end_date
        ).order_by('start_time')

        print(f"Found {events.count()} events")
        # Debug: Print each event's start time
        for event in events:
            print(f"Event: {event.title}, Start Time: {event.start_time}")

        serializer = EventSerializer(events, many=True, context={'user': request.user})
        return Response({
            'message': 'Successfully retrieved events',
            'data': serializer.data,
            'month_info': {
                'year': year,
                'month': month,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }, status=HTTPStatus.OK)

    except ValueError as e:
        return Response({
            'error': str(e)
        }, status=HTTPStatus.BAD_REQUEST)
    except Exception as e:
        print(f"Error in get_creator_events_by_month: {str(e)}")
        return Response({
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_events_starting_next_hour(request):
    """
    Get the closest event that is starting within the next 6 hours or occurred in the past 6 hours
    for the authenticated user. This endpoint fetches the event created by the user so they can start it.
    """
    try:
        # Get the current user's creator object
        creator = Creator.objects.get(user=request.user)
        
        # Get current time and time windows (6 hours before and after now)
        now = timezone.now()
        six_hours_from_now = now + timedelta(hours=6)
        six_hours_ago = now - timedelta(hours=6)
        
        # Query for events (created by the user) within the time window
        # Using exclude() instead of __ne which is not supported
        events_in_window = Event.objects.filter(
            creator=creator,
            start_time__gte=six_hours_ago,
            start_time__lte=six_hours_from_now
        ).exclude(
            vision__status='vod'  # Exclude events with vision status 'vod'
        ).order_by('start_time')

        print(f"Events in window: {events_in_window.count()}")
        
        if not events_in_window:
            return Response({
                'message': 'No events found within 6 hours of current time',
                'data': None,
                'time_window': {
                    'start': six_hours_ago.isoformat(),
                    'end': six_hours_from_now.isoformat(),
                    'now': now.isoformat()
                }
            }, status=HTTPStatus.OK)
        
        # Find the closest event to now
        closest_event = min(events_in_window, key=lambda event: abs(event.start_time - now))
        print(f"Closest event: {closest_event}")
        
        # Serialize the event
        serializer = EventSerializer(closest_event, context={'user': request.user})

        print("Serializer data:")
        print(serializer.data)
        
        return Response({
            'message': 'Successfully retrieved closest event',
            'data': serializer.data,
            'time_window': {
                'start': six_hours_ago.isoformat(),
                'end': six_hours_from_now.isoformat(),
                'now': now.isoformat()
            }
        }, status=HTTPStatus.OK)
        
    except Creator.DoesNotExist:
        return Response({
            'message': 'Creator profile not found',
            'error': True
        }, status=HTTPStatus.NOT_FOUND)
    except Exception as e:
        logger.error(f"Error in get_events_starting_next_hour: {str(e)}")
        return Response({
            'message': 'There was an error',
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def get_trending_events_view(request):
    """
    API view that calls the get_trending_events helper function and returns a proper Response object.
    """
    try:
        interest = request.GET.get('interest')
        # Call the helper function (which returns a list)
        events = get_trending_events(request.user, interest)
        
        # Apply pagination
        paginator = PageNumberPagination()
        paginator.page_size = 10
        page_results = paginator.paginate_queryset(events, request)
        
        # Serialize results
        serializer = EventSerializer(page_results, many=True, context={'user': request.user})
        
        # Return paginated response
        return paginator.get_paginated_response(serializer.data)
    except Exception as e:
        logger.error(f"Error in get_trending_events_view: {e}")
        return Response({
            'message': 'There was an error getting trending events', 
            'error': str(e)
        }, status=HTTPStatus.INTERNAL_SERVER_ERROR)
