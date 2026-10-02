import os

from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone as _tz

from pftracker.utils import fy_start_from_label, fy_start_year
from tracker.models import AccountGroup
from portfolio.emails import build_fy_review_context, send_html_email
from portfolio.templatetags.indian_format import inr


class Command(BaseCommand):
    help = 'Sends the financial-year review (run on 1 April after the March snapshot).'

    def add_arguments(self, parser):
        parser.add_argument('--fy', help="FY to review, e.g. 'FY 2025-26'. Defaults to the FY that just closed.")
        parser.add_argument('--preview', metavar='PATH', help='Write the rendered HTML to PATH instead of sending.')

    def handle(self, *args, **options):
        target_email = os.environ.get('VAULT_REPORT_EMAIL', 'admin@example.com')
        if options.get('fy'):
            fy_start = fy_start_from_label(options['fy'])
            if fy_start is None:
                raise CommandError("Use the format 'FY 2025-26'.")
        else:
            fy_start = fy_start_year(_tz.localdate()) - 1

        group = AccountGroup.objects.first()
        if not group:
            self.stdout.write(self.style.ERROR('No household group found.'))
            return

        ctx = build_fy_review_context(group, fy_start)
        html = render_to_string('emails/fy_review.html', ctx)
        if options.get('preview'):
            with open(options['preview'], 'w') as f:
                f.write(html)
            self.stdout.write(self.style.SUCCESS(f"Preview written to {options['preview']}"))
            return

        verdict = {'achieved': 'Target achieved', 'partial': 'Partly achieved',
                   'missed': 'Target missed'}.get(ctx['verdict'], 'Year in review')
        lines = [f"Vault {ctx['fy']} review — {verdict}", '',
                 f"Closing net worth: {inr(ctx['close_value'])}"]
        if ctx['year']:
            y = ctx['year']
            lines.append(f"Change: {inr(y['change'])} ({y['change_pct']}%) — fresh money {inr(y['money_added'])}, "
                         f"market {inr(y['market'])}")
        lines += [f"{g['label']} {inr(g['target'])}: {'achieved' if g['achieved'] else 'missed'} ({g['pct']}%)"
                  for g in ctx['goals']]

        try:
            send_html_email(f"Vault {ctx['fy']} review · {verdict}", '\n'.join(lines), html, [target_email])
            self.stdout.write(self.style.SUCCESS(f'Sent {ctx["fy"]} review to {target_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))
