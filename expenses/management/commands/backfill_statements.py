import datetime
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import GmailAccount
from expenses.sync import BACKFILL_MAX_MESSAGES, backfill_statements

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Scans connected Gmail accounts for credit-card statement emails and PDFs, '
        'backfilling missing expenses while preventing duplicates.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            help='Only backfill for this connected Gmail address.',
        )
        parser.add_argument(
            '--since',
            help='Starting date (YYYY-MM-DD or YYYY-MM). Defaults to 180 days ago.',
        )
        parser.add_argument(
            '--budget',
            type=int,
            default=0,
            help='Time limit in seconds per mailbox (0 = unlimited).',
        )
        parser.add_argument(
            '--max-messages',
            type=int,
            default=BACKFILL_MAX_MESSAGES,
            help=f'Max candidate messages to inspect per account (default {BACKFILL_MAX_MESSAGES}).',
        )

    def handle(self, *args, **options):
        # Resolve since date
        since_opt = options.get('since')
        if since_opt:
            parts = since_opt.strip().split('-')
            if len(parts) == 2:
                since = datetime.date(int(parts[0]), int(parts[1]), 1)
            elif len(parts) == 3:
                since = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
            else:
                self.stderr.write(self.style.ERROR(f'Invalid --since date "{since_opt}". Use YYYY-MM-DD or YYYY-MM.'))
                return
        else:
            since = timezone.localdate() - datetime.timedelta(days=180)

        accounts = GmailAccount.objects.filter(is_active=True).select_related('group', 'user')
        if options.get('email'):
            accounts = accounts.filter(email=options['email'].strip().lower())

        if not accounts.exists():
            self.stdout.write('No active Gmail accounts found to backfill.')
            return

        self.stdout.write(self.style.NOTICE(f'Starting credit card statement backfill since {since}...'))

        total_scanned = 0
        total_statements = 0
        total_added = 0
        total_review = 0

        for account in accounts:
            self.stdout.write(f'Scanning {account.email}...')
            res = backfill_statements(
                account=account,
                since=since,
                time_budget=options.get('budget') or None,
                max_messages=options.get('max_messages') or BACKFILL_MAX_MESSAGES,
            )
            if res.error:
                self.stderr.write(self.style.ERROR(f'  {account.email} error: {res.error}'))
                continue

            total_scanned += res.scanned
            total_statements += res.statements
            total_added += res.lines_added
            total_review += res.lines_review

            self.stdout.write(self.style.SUCCESS(
                f'  {account.email}: scanned {res.scanned} emails -> '
                f'{res.statements} statements ({res.parsed} parsed, {res.duplicates} duplicates, {res.locked} locked). '
                f'Expenses added: {res.lines_added}, parked for review: {res.lines_review}'
            ))

        self.stdout.write(self.style.SUCCESS(
            f'Backfill complete: {total_statements} statements processed, {total_added} missing transactions backfilled, '
            f'{total_review} parked for user review.'
        ))
