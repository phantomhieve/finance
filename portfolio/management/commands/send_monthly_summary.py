import datetime
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone as _tz

from tracker.models import AccountGroup
from portfolio.models import PortfolioInsight, InsightGenerationSettings
from portfolio.services import get_portfolio_summary, get_growth_data
from portfolio.ai import build_prompt_data, call_gemini
from portfolio.emails import build_monthly_context, send_html_email
from portfolio.templatetags.indian_format import inr


class Command(BaseCommand):
    help = 'Sends the monthly AI portfolio summary to the household head.'

    def add_arguments(self, parser):
        parser.add_argument('--preview', metavar='PATH',
                            help='Write the rendered HTML to PATH instead of sending (skips AI generation).')

    def handle(self, *args, **options):
        preview = options.get('preview')

        group = AccountGroup.objects.first()
        if not group:
            self.stdout.write(self.style.ERROR('No household group found.'))
            return

        target_email = (
            os.environ.get('VAULT_REPORT_EMAIL')
            or getattr(settings, 'VAULT_REPORT_EMAIL', '')
            or getattr(settings, 'EMAIL_HOST_USER', '')
        )
        if not target_email:
            primary = group.members.filter(user_type='PRIMARY').first()
            target_email = primary.email if primary and primary.email else ''
        if not target_email and not preview:
            self.stdout.write(self.style.ERROR('No recipient email configured. Set VAULT_REPORT_EMAIL in .env.'))
            return

        # 1. Refresh AI insights if the cooldown has passed
        latest = PortfolioInsight.objects.filter(group=group).order_by('-generated_at').first()
        cooldown = datetime.timedelta(days=InsightGenerationSettings.get_solo().cooldown_days)
        can_generate = not preview and (latest is None or (_tz.now() - latest.generated_at) >= cooldown)

        if can_generate:
            self.stdout.write('AI insight cooldown has passed. Generating new insights...')
            try:
                summary = get_portfolio_summary(group)
                growth = get_growth_data(group=group)
                prompt_data = build_prompt_data(summary, growth, group)
                result = call_gemini(prompt_data, group=group)
                latest = PortfolioInsight.objects.create(
                    group=group,
                    model_used=result.model,
                    prompt_data=prompt_data,
                    insights=result.insights_dict,
                )
                self.stdout.write(self.style.SUCCESS('Successfully generated new AI insights.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to generate AI insights: {e}'))
        else:
            self.stdout.write('Using the latest available AI insights.')

        # 2. Render and send
        ctx = build_monthly_context(group, latest.insights if latest else None)
        html = render_to_string('emails/monthly_summary.html', ctx)

        if preview:
            with open(preview, 'w') as f:
                f.write(html)
            self.stdout.write(self.style.SUCCESS(f'Preview written to {preview}'))
            return

        lines = [f"Vault monthly review — {ctx['month']}", '',
                 f"Net worth: {inr(ctx['total_value'])}"]
        if ctx['since']:
            lines.append(f"Change since {ctx['since']['month']:%b %Y}: {inr(ctx['since']['change'])} "
                         f"({ctx['since']['change_pct']}%) — fresh money {inr(ctx['since']['money_added'])}, "
                         f"market {inr(ctx['since']['market'])}")
        if ctx['goal']:
            g = ctx['goal']
            lines.append(f"{ctx['goal_fy']} target {inr(g['target'])}: {g.get('fy_progress_pct', g['pct'])}% there")
        if ctx['insights']:
            lines += ['', f"Health score: {ctx['insights'].get('score')}/100",
                      ctx['insights'].get('summary', '')]

        try:
            send_html_email(f"Vault monthly review · {_tz.now():%b %Y}", '\n'.join(lines), html, [target_email])
            self.stdout.write(self.style.SUCCESS(f'Successfully sent monthly summary to {target_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))
