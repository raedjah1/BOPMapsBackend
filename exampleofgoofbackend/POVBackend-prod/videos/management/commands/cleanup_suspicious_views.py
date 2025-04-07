import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count, Q, F
from django.db import transaction
from users.models import WatchHistory, ViewCount
from videos.models import Vision

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Identify and clean up suspicious views that may be from bots"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Run in dry-run mode (no changes will be made)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        self.stdout.write(f"Running {'in dry-run mode' if dry_run else 'in live mode'}")

        # Get timestamp for one week ago
        one_week_ago = timezone.now() - timezone.timedelta(days=7)

        # Identify suspicious IPs (too many views in a day)
        suspicious_ips = ViewCount.objects.filter(
            timestamp__gte=one_week_ago
        ).values('ip_address').annotate(
            view_count=Count('id')
        ).filter(
            view_count__gt=200,
            ip_address__isnull=False
        ).values_list('ip_address', flat=True)

        self.stdout.write(f"Found {len(suspicious_ips)} suspicious IPs")

        # Identify users with suspiciously high view activity
        suspicious_users = ViewCount.objects.filter(
            timestamp__gte=one_week_ago
        ).values('user').annotate(
            view_count=Count('id')
        ).filter(
            view_count__gt=300
        ).values_list('user', flat=True)

        self.stdout.write(f"Found {len(suspicious_users)} suspicious users")

        # Identify suspicious rapid viewing patterns (too many views in a short time)
        # Find users who viewed many videos in a very short time
        rapid_viewing_users = []
        for user_id in ViewCount.objects.values_list('user', flat=True).distinct():
            views = list(ViewCount.objects.filter(
                user_id=user_id, 
                timestamp__gte=one_week_ago
            ).order_by('timestamp').values('timestamp', 'vision'))
            
            if len(views) < 10:
                continue
                
            # Look for clusters of views within short time periods
            rapid_clusters = 0
            for i in range(len(views) - 5):
                time_diff = views[i+5]['timestamp'] - views[i]['timestamp']
                if time_diff.total_seconds() < 60:  # 5 videos in under a minute
                    rapid_clusters += 1
            
            if rapid_clusters > 3:  # Multiple clusters of rapid viewing
                rapid_viewing_users.append(user_id)
                self.stdout.write(f"User {user_id} shows rapid viewing pattern: {rapid_clusters} clusters")
        
        self.stdout.write(f"Found {len(rapid_viewing_users)} users with suspicious rapid viewing patterns")
        
        # Find views with suspicious patterns
        suspicious_views = ViewCount.objects.filter(
            Q(ip_address__in=suspicious_ips) | 
            Q(user__in=suspicious_users) |
            Q(user__in=rapid_viewing_users) |
            Q(is_valid=False)  # Include any views already marked as invalid
        )

        # Get distinct vision IDs from suspicious watch histories
        affected_visions = suspicious_views.values_list('vision', flat=True).distinct()
        
        # Count and log
        suspicious_view_count = suspicious_views.count()
        self.stdout.write(f"Found {suspicious_view_count} suspicious views affecting {len(affected_visions)} visions")
        
        if not dry_run:
            with transaction.atomic():
                # Mark all suspicious views as invalid
                suspicious_views.update(is_valid=False)
                self.stdout.write(f"Marked {suspicious_view_count} views as invalid")
                
                # Adjust view counts for affected visions
                for vision_id in affected_visions:
                    try:
                        vision = Vision.objects.get(pk=vision_id)
                        
                        # Count suspicious views for this vision that were previously valid
                        invalid_views = suspicious_views.filter(
                            vision=vision_id,
                            is_valid=False
                        ).count()
                        
                        # Get accurate count of valid views from ViewCount table
                        valid_views = ViewCount.objects.filter(
                            vision=vision_id,
                            is_valid=True
                        ).count()
                        
                        # Update vision's view count to the accurate count
                        old_count = vision.views
                        vision.views = valid_views
                        vision.save(update_fields=['views'])
                        
                        self.stdout.write(f"Adjusted view count for vision {vision_id} from {old_count} to {valid_views}")
                    except Vision.DoesNotExist:
                        self.stdout.write(f"Vision {vision_id} no longer exists")
            
            self.stdout.write(f"Updated view counts for {len(affected_visions)} visions")
        else:
            self.stdout.write("Dry run - no changes made")

        self.stdout.write(self.style.SUCCESS('Successfully cleaned up suspicious views')) 