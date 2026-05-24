import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from intel_app.models import MobileMoneyAlert

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Deletes Expired and Ignored MoMo alerts older than N days. Keeps Claimed/Unclaimed."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would be deleted without deleting.')
        parser.add_argument('--days', type=int, default=30,
                            help='Retention window in days (default 30).')

    def handle(self, *args, **opts):
        cutoff = timezone.now() - timedelta(days=opts['days'])
        junk = MobileMoneyAlert.objects.filter(
            status__in=['Expired', 'Ignored'],
            created_at__lt=cutoff,
        )
        n = junk.count()
        if n == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to clean."))
            return

        if opts['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"[DRY RUN] Would delete {n} alerts."))
            return

        deleted, _ = junk.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} old alerts."))
        logger.info("Scheduled cleanup deleted %d MoMo alerts.", deleted)
