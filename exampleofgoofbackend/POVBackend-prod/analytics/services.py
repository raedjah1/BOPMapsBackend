# analytics/services.py
import asyncio
from asgiref.sync import sync_to_async
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from django.db.models import Sum, Count, Avg, F, FloatField
from analytics.models import ViewSnapshot, RevenueSnapshot, EngagementSnapshot, DemographicSnapshot, SubscriptionSnapshot
from videos.models import Vision
from payments.models import Tip
from subscriptions.models import Subscription
from decimal import Decimal

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self, creator, time_span):
        self.creator = creator
        self.time_span = time_span
        self.end_date = timezone.now()
        self.start_date = self.end_date - timedelta(days=self.time_span)

    def to_decimal(self, value):
        """Convert a value to Decimal with proper handling of different types"""
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

    def get_primary_metrics(self):
        """Get total views, engagement rate, and average session duration"""
        try:
            visions = Vision.objects.filter(
                creator=self.creator,
                created_at__range=(self.start_date, self.end_date)
            )
            
            # Combine aggregate calls into one query for consistency
            aggregated = visions.aggregate(
                total_views=Sum('views'),
                total_likes=Sum('likes'),
                total_comments=Count('comment')
            )
            total_views = aggregated.get('total_views') or 0
            total_likes = aggregated.get('total_likes') or 0
            total_comments = aggregated.get('total_comments') or 0
            
            total_engagements = self.to_decimal(total_likes + total_comments)
            total_views_decimal = self.to_decimal(total_views)
            
            engagement_rate = (
                (total_engagements / total_views_decimal) * Decimal('100')
                if total_views else Decimal('0')
            )
            avg_session_duration = Decimal('0')
            
            return total_views, engagement_rate, avg_session_duration
        except Exception as e:
            logger.error(f"Error in get_primary_metrics: {e}")
            return 0, Decimal('0'), Decimal('0')

    def get_breakdowns(self):
        """Calculate demographic breakdowns based on subscriptions"""
        try:
            # Get all active subscriptions for this creator
            subscriptions = Subscription.objects.filter(
                creator=self.creator,
                end_date__gte=self.end_date  # Only active subscriptions
            ).select_related('spectator__user')  # Changed from subscriber to spectator
            
            # Initialize counters
            age_brackets = {
                "18-24": 0,
                "25-34": 0,
                "35-44": 0,
                "45-54": 0,
                "55+": 0,
                "unknown": 0
            }
            
            gender_brackets = {
                "M": 0,
                "F": 0,
                "O": 0,
                "unknown": 0
            }
            
            country_brackets = {}
            
            # Count demographics from subscriptions
            for sub in subscriptions:
                user = sub.spectator.user  # Changed from subscriber to spectator
                
                # Age calculation
                if hasattr(user, 'birth_date') and user.birth_date:
                    today = timezone.now().date()
                    birth_date = user.birth_date
                    
                    # Calculate age more accurately
                    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    
                    # Validate age is at least 18
                    if age < 18:
                        # Skip users under 18 or with clearly incorrect birth dates
                        age_brackets["unknown"] += 1
                    elif age < 25:
                        age_brackets["18-24"] += 1
                    elif age < 35:
                        age_brackets["25-34"] += 1
                    elif age < 45:
                        age_brackets["35-44"] += 1
                    elif age < 55:
                        age_brackets["45-54"] += 1
                    else:
                        age_brackets["55+"] += 1
                else:
                    age_brackets["unknown"] += 1
                
                # Gender breakdown
                if hasattr(user, 'gender') and user.gender:
                    gender = user.gender
                    if gender in gender_brackets:
                        gender_brackets[gender] += 1
                    else:
                        gender_brackets["O"] += 1
                else:
                    gender_brackets["unknown"] += 1
                
                # Country breakdown
                if hasattr(user, 'country') and user.country:
                    country = user.country
                    country_brackets[country] = country_brackets.get(country, 0) + 1
                else:
                    country_brackets["unknown"] = country_brackets.get("unknown", 0) + 1
            
            # Sort countries by count, get top 5
            top_countries = dict(sorted(
                country_brackets.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5])
            
            return age_brackets, gender_brackets, top_countries
        except Exception as e:
            logger.error(f"Error in get_breakdowns: {e}")
            return {}, {}, {}

    def get_financial_metrics(self):
        """Get financial metrics including tips and subscriptions"""
        try:
            # Calculate tips
            tips = Tip.objects.filter(
                creator=self.creator,
                created_at__range=(self.start_date, self.end_date)
            )
            total_tips = self.to_decimal(tips.aggregate(Sum('amount'))['amount__sum'] or 0)

            # Calculate subscription metrics
            subscriptions = Subscription.objects.filter(
                creator=self.creator,
                start_date__lte=self.end_date,
                end_date__gte=self.start_date
            )
            
            # Total active subscriptions
            total_subscribers = subscriptions.count()
            
            # New subscriptions in this period
            new_subscribers = subscriptions.filter(
                start_date__range=(self.start_date, self.end_date)
            ).count()
            
            # Churned subscriptions in this period
            churned_subscribers = Subscription.objects.filter(
                creator=self.creator,
                end_date__range=(self.start_date, self.end_date)
            ).count()

            # Calculate revenue using creator's subscription price
            subscription_price = self.to_decimal(self.creator.subscription_price or 0)
            subscription_revenue = subscription_price * self.to_decimal(total_subscribers)
            total_revenue = total_tips + subscription_revenue
            tip_percentage = (total_tips / total_revenue * Decimal('100')) if total_revenue else Decimal('0')

            return (
                total_tips, 
                subscription_revenue, 
                total_revenue, 
                tip_percentage, 
                new_subscribers,
                total_subscribers,
                churned_subscribers
            )
        except Exception as e:
            logger.error(f"Error in get_financial_metrics: {e}")
            return Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'), 0, 0, 0

    def get_engagement_metrics(self):
        """Get average likes and comments per vision"""
        try:
            visions = Vision.objects.filter(
                creator=self.creator,
                created_at__range=(self.start_date, self.end_date)
            )
            
            total_visions = visions.count()
            if total_visions > 0:
                metrics = visions.aggregate(
                    avg_likes=Avg('likes'),
                    total_comments=Count('comment')
                )
                avg_likes = metrics['avg_likes'] or 0
                avg_comments = (metrics['total_comments'] or 0) / total_visions
                metrics = {'avg_likes': avg_likes, 'avg_comments': avg_comments}
            else:
                metrics = {'avg_likes': 0, 'avg_comments': 0}
            
            return metrics['avg_likes'] or 0, metrics['avg_comments'] or 0
        except Exception as e:
            logger.error(f"Error in get_engagement_metrics: {e}")
            return 0, 0
        

    def get_demographics_data(self):
        """Get demographic breakdowns from latest snapshot"""
        try:
            latest_demographic = DemographicSnapshot.objects.filter(
                creator=self.creator,
                date__range=(self.start_date, self.end_date)
            ).order_by('-date').first()

            return {
                'age_breakdown': latest_demographic.age_breakdown if latest_demographic else {},
                'gender_breakdown': latest_demographic.gender_breakdown if latest_demographic else {},
                'top_countries': latest_demographic.country_breakdown if latest_demographic else {}
            }
        except Exception as e:
            logger.error(f"Error getting demographics data: {e}")
            return {'age_breakdown': {}, 'gender_breakdown': {}, 'top_countries': {}}

    def get_latest_analytics_data(self):
        """Get aggregated high-level metrics over the selected time span using daily snapshots"""
        try:
            # Aggregate new subscribers from daily snapshots
            subscriptions_agg = SubscriptionSnapshot.objects.filter(
                creator=self.creator,
                date__range=(self.start_date, self.end_date)
            ).aggregate(new_subscribers=Sum('new_subscribers'))
            new_subscribers = subscriptions_agg.get('new_subscribers') or 0

            # Aggregate total views from daily snapshots
            views_agg = ViewSnapshot.objects.filter(
                creator=self.creator,
                date__range=(self.start_date, self.end_date)
            ).aggregate(total_views=Sum('total_views'))
            total_views = views_agg.get('total_views') or 0

            # Aggregate total revenue from daily snapshots
            revenue_agg = RevenueSnapshot.objects.filter(
                creator=self.creator,
                date__range=(self.start_date, self.end_date)
            ).aggregate(total_revenue=Sum('total_revenue'))
            total_revenue = revenue_agg.get('total_revenue') or Decimal('0')

            return {
                'new_subscribers': new_subscribers,
                'total_views': total_views,
                'total_revenue': round(total_revenue, 2)
            }
        except Exception as e:
            logger.error(f"Error getting aggregated analytics data: {e}")
            return {'new_subscribers': 0, 'total_views': 0, 'total_revenue': 0}

    def get_detailed_analytics_data_points(self):
        """Get daily financial metrics"""
        try:
            # Get all snapshots for the date range in bulk
            revenue_snapshots = {
                snap.date: snap for snap in RevenueSnapshot.objects.filter(
                    creator=self.creator,
                    date__range=(self.start_date, self.end_date)
                )
            }
            
            view_snapshots = {
                snap.date: snap for snap in ViewSnapshot.objects.filter(
                    creator=self.creator,
                    date__range=(self.start_date, self.end_date)
                )
            }

            daily_points = []
            dates = [
                self.start_date.date() + timedelta(days=x) 
                for x in range((self.end_date.date() - self.start_date.date()).days + 1)
            ]

            # Process the data without threading
            for current_date in dates:
                daily_revenue = revenue_snapshots.get(current_date)
                daily_view = view_snapshots.get(current_date)

                if daily_revenue and daily_view:
                    daily_points.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'views': daily_view.total_views,
                        'tip_revenue': round(daily_revenue.tip_revenue, 2),
                        'subscription_revenue': round(daily_revenue.subscription_revenue, 2),
                        'tip_percentage': round(daily_revenue.tip_percentage, 2),
                        'total_tips': round(daily_revenue.tip_revenue, 2),
                        'total_revenue': round(daily_revenue.total_revenue, 2)
                    })

            return daily_points
        except Exception as e:
            logger.error(f"Error getting detailed analytics data points: {e}")
            return []

    def get_audience_analytics_data_points(self):
        """Get daily audience engagement metrics"""
        try:
            # Fetch all snapshots for the date range in bulk
            subscription_snapshots = {
                snap.date: snap for snap in SubscriptionSnapshot.objects.filter(
                    creator=self.creator,
                    date__range=(self.start_date, self.end_date)
                )
            }
            
            engagement_snapshots = {
                snap.date: snap for snap in EngagementSnapshot.objects.filter(
                    creator=self.creator,
                    date__range=(self.start_date, self.end_date)
                )
            }
            
            view_snapshots = {
                snap.date: snap for snap in ViewSnapshot.objects.filter(
                    creator=self.creator,
                    date__range=(self.start_date, self.end_date)
                )
            }

            daily_points = []
            dates = [
                self.start_date.date() + timedelta(days=x) 
                for x in range((self.end_date.date() - self.start_date.date()).days + 1)
            ]

            # Process the data without threading
            for current_date in dates:
                daily_subscription = subscription_snapshots.get(current_date)
                daily_engagement = engagement_snapshots.get(current_date)
                daily_view = view_snapshots.get(current_date)

                if daily_subscription and daily_engagement and daily_view:
                    daily_points.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'total_subscribers': daily_subscription.total_subscribers,
                        'total_likes': daily_engagement.total_likes,
                        'total_comments': daily_engagement.total_comments,
                        'unique_engagers': daily_engagement.unique_engagers,
                        'likes_per_video': round(daily_engagement.avg_likes_per_vision, 2),
                        'comments_per_video': round(daily_engagement.avg_comments_per_vision, 2),
                        'unique_tippers': 0,  # TODO: Add to TipSnapshot model
                        'avg_session_duration': round(daily_view.avg_session_duration, 2),
                        'new_subscribers': daily_subscription.new_subscribers,
                        'churned_subscribers': daily_subscription.churned_subscribers,
                        'engagement_rate': round(daily_view.engagement_rate, 2)
                    })

            return daily_points
        except Exception as e:
            logger.error(f"Error getting audience analytics data points: {e}")
            return []

    def get_analytics_data(self):
        """Get all analytics data with caching"""
        try:
            cache_key = f"analytics_data_{self.creator.pk}_{self.time_span}"
            cached_result = cache.get(cache_key)

            if cached_result:
                return cached_result

            analytics_data = {
                'time_span': f'{self.time_span} days',
                **self.get_latest_analytics_data(),
                **self.get_demographics_data(),
                'detailed_daily_points': self.get_detailed_analytics_data_points(),
                'audience_daily_points': self.get_audience_analytics_data_points()
            }

            # Cache the results for 1 hour
            cache.set(cache_key, analytics_data, timeout=3600)
            return analytics_data

        except Exception as e:
            logger.error(f"Error generating analytics data: {str(e)}")
            return {'error': 'An error occurred while generating analytics data'}
