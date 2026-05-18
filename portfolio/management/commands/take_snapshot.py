import datetime
import logging

from django.core.management.base import BaseCommand

from portfolio.services import take_monthly_snapshot
from tracker.models import AccountGroup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Take a monthly snapshot of the current portfolio state for all groups.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--month',
            type=str,
            default=None,
            help='Month to snapshot (YYYY-MM-DD format, first of month). Defaults to previous month.',
        )

    def handle(self, *args, **options):
        month = None
        if options['month']:
            try:
                month = datetime.datetime.strptime(options['month'], '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {options['month']}. Use YYYY-MM-DD."))
                return

        if month is None:
            today = datetime.date.today()
            if today.month == 1:
                month = datetime.date(today.year - 1, 12, 1)
            else:
                month = datetime.date(today.year, today.month - 1, 1)

        for group in AccountGroup.objects.all().only('id', 'name'):
            result = take_monthly_snapshot(month, group=group)
            if result is None:
                logger.debug("No portfolio data for group %s, skipping snapshot", group.name)
                continue
            snapshot, created = result
            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f"[{group.name}] {verb} snapshot for {snapshot.month:%b %Y}: "
                f"₹{snapshot.total_current_value:,.0f} total, "
                f"₹{snapshot.money_added_this_month:,.0f} added, "
                f"₹{snapshot.returns_this_month:,.0f} returns"
            ))
