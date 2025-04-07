from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Sum, Q, Min
from datetime import timedelta, datetime
from decimal import Decimal
import concurrent.futures
from collections import deque

from users.models import Creator, WatchHistory
from videos.models import Vision
from .models import (
    SubscriptionSnapshot, ViewSnapshot, TipSnapshot,
    EngagementSnapshot, DemographicSnapshot, RevenueSnapshot
)
from .services import AnalyticsService
import logging
from django.db.utils import IntegrityError

logger = logging.getLogger(__name__)

def create_snapshot_for_date(creator_id, target_date):
    try:
        creator = Creator.objects.get(pk=creator_id)
        # Create analytics service instance for this creator
        # Store current time
        current_time = timezone.now()
        
        # Temporarily set timezone.now to return our target date
        def mock_now():
            # Ensure we return a timezone-aware datetime
            naive_dt = datetime.combine(target_date, current_time.time())
            return timezone.make_aware(naive_dt)
        
        original_now = timezone.now
        timezone.now = mock_now
        
        try:
            # Create analytics service instance for this creator
            analytics = AnalyticsService(creator, time_span=1)
            
            # Helper function to convert values to Decimal
            def to_decimal(value):
                if value is None:
                    return Decimal('0')
                if isinstance(value, Decimal):
                    return value
                if isinstance(value, float):
                    # Convert float to string first to avoid precision issues
                    return Decimal(str(value))
                if isinstance(value, (int, str)):
                    return Decimal(str(value))
                raise TypeError(f"Cannot convert {type(value)} to Decimal")

            # Patch the analytics service to use Decimal
            original_to_decimal = getattr(analytics, 'to_decimal', None)
            analytics.to_decimal = to_decimal
            
            try:
                # Get all metrics
                total_views, engagement_rate, avg_session_duration = analytics.get_primary_metrics()
                age_breakdown, gender_breakdown, top_countries = analytics.get_breakdowns()
                
                # Get financial metrics with proper decimal conversion
                (
                    total_tips, 
                    subscription_revenue, 
                    total_revenue, 
                    tip_percentage, 
                    new_subscribers,
                    total_subscribers,
                    churned_subscribers
                ) = analytics.get_financial_metrics()

                # Ensure all financial values are Decimal
                total_tips = to_decimal(total_tips)
                subscription_revenue = to_decimal(subscription_revenue)
                total_revenue = to_decimal(total_revenue)
                tip_percentage = to_decimal(tip_percentage)

                # Convert rate to Decimal if it's not None
                engagement_rate = to_decimal(engagement_rate) if engagement_rate is not None else None

                avg_likes_per_vision, avg_comments_per_vision = analytics.get_engagement_metrics()
            finally:
                # Restore original to_decimal if it existed
                if original_to_decimal:
                    analytics.to_decimal = original_to_decimal
                else:
                    delattr(analytics, 'to_decimal')
        finally:
            # Restore original timezone.now
            timezone.now = original_now

        # Update or create all snapshots in a single transaction
        with transaction.atomic():
            # Update or create subscription snapshot
            SubscriptionSnapshot.objects.update_or_create(
                creator=creator,
                date=target_date,
                defaults={
                    'total_subscribers': total_subscribers,
                    'new_subscribers': new_subscribers,
                    'churned_subscribers': churned_subscribers,
                    'subscription_revenue': subscription_revenue
                }
            )

            # Update or create view snapshot
            ViewSnapshot.objects.update_or_create(
                creator=creator,
                date=target_date,
                defaults={
                    'total_views': total_views,
                    'engagement_rate': engagement_rate,
                    'avg_session_duration': avg_session_duration
                }
            )

            # Update or create demographic snapshot
            DemographicSnapshot.objects.update_or_create(
                creator=creator,
                date=target_date,
                defaults={
                    'age_breakdown': age_breakdown,
                    'gender_breakdown': gender_breakdown,
                    'country_breakdown': top_countries
                }
            )

            # Update or create revenue snapshot
            RevenueSnapshot.objects.update_or_create(
                creator=creator,
                date=target_date,
                defaults={
                    'subscription_revenue': subscription_revenue,
                    'tip_revenue': total_tips,
                    'total_revenue': total_revenue,
                    'tip_percentage': tip_percentage
                }
            )

            # Calculate unique engagers using WatchHistory:
            # Unique engagers for the day are the users that watched any vision today,
            # excluding those who have watched any vision before today.
            unique_engagers = WatchHistory.objects.filter(
                vision__creator=creator,
                watched_at__date=target_date
            ).exclude(
                user__in=WatchHistory.objects.filter(
                    vision__creator=creator,
                    watched_at__date__lt=target_date
                ).values_list('user', flat=True)
            ).values_list('user', flat=True).distinct().count()

            # Update or create engagement snapshot, including the unique engagers count
            EngagementSnapshot.objects.update_or_create(
                creator=creator,
                date=target_date,
                defaults={
                    'avg_likes_per_vision': avg_likes_per_vision,
                    'avg_comments_per_vision': avg_comments_per_vision,
                    'unique_engagers': unique_engagers
                }
            )

        logger.info(f"Successfully created/updated snapshots for creator {creator.pk} on {target_date}")
        return True

    except Exception as e:
        logger.error(f"Error creating snapshots for creator {creator.pk} on {target_date}: {str(e)}")
        return False

def process_creator_snapshots(creator_id, start_date, end_date):
    """Process all missing snapshots for a single creator within a date range"""
    creator = Creator.objects.get(pk=creator_id)
    current_date = start_date
    results = []
    
    while current_date <= end_date:
        # Check if snapshot exists for this date
        has_snapshot = (
            SubscriptionSnapshot.objects.filter(creator=creator, date=current_date).exists() and
            ViewSnapshot.objects.filter(creator=creator, date=current_date).exists() and
            DemographicSnapshot.objects.filter(creator=creator, date=current_date).exists() and
            RevenueSnapshot.objects.filter(creator=creator, date=current_date).exists() and
            EngagementSnapshot.objects.filter(creator=creator, date=current_date).exists()
        )
        
        if not has_snapshot:
            result = create_snapshot_for_date(creator_id, current_date)
            results.append(result)
        
        current_date += timedelta(days=1)
    return results

def create_daily_snapshots():
    """Create snapshots for all creators in parallel"""
    yesterday = timezone.now().date() - timedelta(days=1)
    results = deque()
    max_workers = 4  # Adjust based on your system's capabilities
    
    # Prepare tasks for each creator
    tasks = []
    for creator in Creator.objects.all():
        # Get the date of the first vision
        first_vision_date = Vision.objects.filter(creator=creator).aggregate(
            first_date=Min('created_at')
        )['first_date']
        
        if not first_vision_date:
            continue
            
        first_vision_date = first_vision_date.date()
        tasks.append((creator.pk, first_vision_date, yesterday))
    
    # Execute tasks in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_creator_snapshots, creator_id, start_date, end_date)
            for creator_id, start_date, end_date in tasks
        ]
        
        # Wait for all tasks to complete
        concurrent.futures.wait(futures)
        
        # Collect results
        for future in futures:
            try:
                result = future.result()
                results.extend(result)
            except Exception as e:
                logger.error(f"Error in snapshot creation: {str(e)}")
    
    return list(results)

def backfill_missing_snapshots():
    """Backfill missing snapshots for all creators in parallel"""
    today = timezone.now().date()
    results = deque()
    max_workers = 8  # Adjust based on your system's capabilities
    
    # Prepare tasks for each creator
    tasks = []
    for creator in Creator.objects.all():
        # Get the date of the first vision
        first_vision_date = Vision.objects.filter(creator=creator).aggregate(
            first_date=Min('created_at')
        )['first_date']
        
        if not first_vision_date:
            continue
            
        first_vision_date = first_vision_date.date()
        tasks.append((creator.pk, first_vision_date, today - timedelta(days=1)))
    
    # Execute tasks in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_creator_snapshots, creator_id, start_date, end_date)
            for creator_id, start_date, end_date in tasks
        ]
        
        # Wait for all tasks to complete
        concurrent.futures.wait(futures)
        
        # Collect results
        for future in futures:
            try:
                result = future.result()
                results.extend(result)
            except Exception as e:
                logger.error(f"Error in snapshot creation: {str(e)}")
    
    return list(results) 