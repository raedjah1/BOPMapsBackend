from django.core.management.base import BaseCommand
from django.utils import timezone
from subscriptions.tasks import process_due_subscriptions, process_ending_subscriptions, process_topup_expirations

class Command(BaseCommand):
    help = 'Process subscriptions that are due for renewal and ending'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'Starting subscription processing at {timezone.now()}'))
        
        # Process topup credit expirations
        self.stdout.write(self.style.SUCCESS('Checking for expired topup credits...'))
        expired_count = process_topup_expirations()
        self.stdout.write(self.style.SUCCESS(f'Expired topup credits for {expired_count} users'))
        
        # Process renewals
        self.stdout.write(self.style.SUCCESS('Processing subscription renewals...'))
        process_due_subscriptions()
        
        # Process ending subscriptions
        self.stdout.write(self.style.SUCCESS('Processing ending subscriptions...'))
        process_ending_subscriptions()
        
        self.stdout.write(self.style.SUCCESS(f'Finished subscription processing at {timezone.now()}')) 