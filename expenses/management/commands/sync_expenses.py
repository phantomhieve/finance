from django.core.management.base import BaseCommand

from expenses.models import GmailAccount
from expenses.sync import sync_account

CRON_MAX_MESSAGES = 2000


class Command(BaseCommand):
    help = 'Pulls new bank / card alert emails from every connected Gmail inbox and records them as expenses.'

    def add_arguments(self, parser):
        parser.add_argument('--email', help='Only sync this connected address.')
        parser.add_argument('--budget', type=int, default=0, help='Seconds per mailbox before stopping (0 = no limit).')

    def handle(self, *args, **options):
        accounts = GmailAccount.objects.filter(is_active=True).select_related('group')
        if options.get('email'):
            accounts = accounts.filter(email=options['email'].lower())
        if not accounts:
            self.stdout.write('No active Gmail accounts to sync.')
            return
        for account in accounts:
            result = sync_account(account, time_budget=options['budget'] or None, max_messages=CRON_MAX_MESSAGES)
            if result.error:
                self.stdout.write(self.style.ERROR(f'{account.email}: {result.error}'))
                continue
            self.stdout.write(self.style.SUCCESS(
                f'{account.email}: {result.transactions} transactions, {result.statements} statements, '
                f'{result.payments} payments, {result.ignored} ignored, {result.errors} errors'
                f'{"" if result.complete else " (partial — will continue next run)"}'
            ))
