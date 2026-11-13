"""Management command to run Gemini AI categorization on daily expenses (intended for daily 2:00 AM cron)."""
from __future__ import annotations

import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses import ai
from expenses.categories import categorise_expenses_with_ai
from expenses.models import Expense
from tracker.models import AccountGroup


class Command(BaseCommand):
    help = 'Categorises previous day expenses using Gemini AI (designed to run daily at 2:00 AM).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            help='Target specific date (YYYY-MM-DD). Defaults to yesterday.',
        )
        parser.add_argument(
            '--days-back',
            type=int,
            default=1,
            help='Days back to process if --date not specified (default: 1 = yesterday).',
        )
        parser.add_argument(
            '--all-pending',
            action='store_true',
            help='Categorise all uncategorised expenses across any date.',
        )

    def handle(self, *args, **options):
        if not ai.ai_available():
            self.stdout.write(self.style.WARNING('Gemini AI is not configured or available.'))
            return

        today = timezone.localdate()
        target_date = None
        if options.get('date'):
            try:
                target_date = datetime.date.fromisoformat(options['date'])
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {options['date']}. Use YYYY-MM-DD."))
                return
        elif not options.get('all_pending'):
            target_date = today - datetime.timedelta(days=options['days_back'])

        groups = AccountGroup.objects.all()
        for group in groups:
            self._process_group(group, target_date, options.get('all_pending', False))

    def _process_group(self, group: AccountGroup, target_date: datetime.date | None, all_pending: bool):
        qs = Expense.objects.filter(
            group=group,
            is_deleted=False,
            category__isnull=True,
            category_source='NONE',
        )
        if all_pending:
            self.stdout.write(f"[{group.name}] Scanning all uncategorised expenses...")
        elif target_date:
            qs = qs.filter(txn_date=target_date)
            self.stdout.write(f"[{group.name}] Scanning expenses for {target_date}...")

        pending = list(qs.order_by('-txn_date', '-id'))
        if not pending:
            self.stdout.write(self.style.SUCCESS(f"[{group.name}] No pending transactions to categorise."))
            return

        self.stdout.write(f"[{group.name}] Found {len(pending)} transactions to evaluate with AI.")
        updated = categorise_expenses_with_ai(group, pending)
        self.stdout.write(self.style.SUCCESS(f"[{group.name}] Successfully categorised {updated} transactions."))
