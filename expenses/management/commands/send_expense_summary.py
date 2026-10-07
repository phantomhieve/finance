from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string

from expenses.emails import build_summary_context, previous_month, recipients, summary_text
from expenses.models import GmailAccount
from portfolio.emails import send_html_email
from tracker.models import AccountGroup


class Command(BaseCommand):
    help = "Emails each household its mail-detected spend for last month, with suspicious transactions flagged."

    def add_arguments(self, parser):
        parser.add_argument('--month', help='YYYY-MM to report on (default: previous month).')
        parser.add_argument('--preview', metavar='PATH', help='Write the HTML to PATH instead of sending (no AI).')

    def handle(self, *args, **options):
        if options.get('month'):
            try:
                year, month = (int(x) for x in options['month'].split('-'))
            except ValueError as exc:
                raise CommandError('--month must look like 2026-03') from exc
        else:
            year, month = previous_month()
        preview = options.get('preview')

        group_ids = GmailAccount.objects.values_list('group_id', flat=True).distinct()
        groups = AccountGroup.objects.filter(pk__in=group_ids)
        if not groups:
            self.stdout.write('No household has a connected Gmail inbox — nothing to send.')
            return

        for group in groups:
            config = getattr(group, 'config', None)
            if config is not None and not config.feature_expenses:
                continue
            ctx = build_summary_context(group, year, month, with_ai=not preview)
            html = render_to_string('emails/expense_summary.html', ctx)
            if preview:
                with open(preview, 'w') as f:
                    f.write(html)
                self.stdout.write(self.style.SUCCESS(f'Preview for {group} written to {preview}'))
                return
            to = recipients(group)
            if not to:
                self.stdout.write(self.style.WARNING(f'{group}: no recipient email addresses.'))
                continue
            subject = f"Household spend · {ctx['month']}"
            if ctx['flagged']:
                subject += f" · {len(ctx['flagged'])} to review"
            try:
                send_html_email(subject, summary_text(ctx), html, to)
                self.stdout.write(self.style.SUCCESS(f'{group}: sent {ctx["month"]} summary to {len(to)} recipient(s).'))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'{group}: failed to send — {exc}'))
