import json
import os

from pydantic import BaseModel
from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from pftracker.ai_gateway import TaskType, gateway
from tracker.models import AccountGroup
from portfolio.ai import _load_investor_profile
from portfolio.emails import apply_floor, build_weekly_context, send_html_email
from portfolio.templatetags.indian_format import inr

DEFAULT_FLOOR = 600000.0


class AIContextItem(BaseModel):
    symbol: str
    context: str


class WeeklyAnalysisResponse(BaseModel):
    safety_floor_inr: float
    items: list[AIContextItem]


class Command(BaseCommand):
    help = 'Sends the weekly equity intelligence brief.'

    def add_arguments(self, parser):
        parser.add_argument('--preview', metavar='PATH',
                            help='Write the rendered HTML to PATH instead of sending.')

    def handle(self, *args, **options):
        preview = options.get('preview')

        group = AccountGroup.objects.first()
        if not group:
            self.stdout.write(self.style.ERROR('No household group found.'))
            return

        target_email = os.environ.get('VAULT_REPORT_EMAIL')
        if not target_email:
            primary = group.members.filter(user_type='PRIMARY').first()
            target_email = primary.email if primary and primary.email else getattr(settings, 'EMAIL_HOST_USER', '')
        if not target_email and not preview:
            self.stdout.write(self.style.ERROR('No recipient email configured. Set VAULT_REPORT_EMAIL in .env.'))
            return

        ctx = build_weekly_context(group)
        floor, ai_notes = self._ai_context(group, ctx['notable'])
        for s in ctx['notable']:
            s['ai'] = ai_notes.get(s['symbol'], '')
        apply_floor(ctx, floor)

        html = render_to_string('emails/weekly_brief.html', ctx)
        if preview:
            with open(preview, 'w') as f:
                f.write(html)
            self.stdout.write(self.style.SUCCESS(f'Preview written to {preview}'))
            return

        status = (f"Shortfall {inr(ctx['deficit'])}" if ctx['deficit']
                  else f"Deployable {inr(ctx['deployable'])}")
        lines = [f"Vault weekly brief — {ctx['date']}", '',
                 f"{status} (reserves {inr(ctx['total_liquid'])} vs floor {inr(floor)})", '']
        lines += [f"{s['symbol']}: {s['pnl_pct']:+.1f}% {s['ai']}".rstrip() for s in ctx['notable']]

        try:
            send_html_email(f"Vault weekly brief · {status}", '\n'.join(lines), html, [target_email])
            self.stdout.write(self.style.SUCCESS(f'Successfully sent weekly brief to {target_email}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to send email: {e}'))

    def _ai_context(self, group, notable):
        """Safety floor from the investor profile + valuation notes for notable positions."""
        if not gateway.is_available(TaskType.REASONING):
            return DEFAULT_FLOOR, {}
        try:
            stocks_json = json.dumps([{'symbol': s['symbol'], 'pnl_pct': round(s['pnl_pct'], 2)} for s in notable])
            prompt = (
                "You are a financial analyst generating a weekly equity brief.\n\n"
                "TASK 1: Extract the safety floor (emergency fund target) in INR from the investor profile below. Return it as a float.\n"
                f"Profile: {_load_investor_profile(group)}\n\n"
                "TASK 2: Provide fundamental valuation context (P/E, yield, moat durability) for these notable stock positions "
                "based on their net performance. Two sentences max per stock.\n"
                f"Stocks: {stocks_json}\n"
            )
            parsed = gateway.generate_structured(
                schema=WeeklyAnalysisResponse,
                prompt=prompt,
                task=TaskType.REASONING,
                temperature=0.2,
            )
            if not parsed:
                return DEFAULT_FLOOR, {}
            self.stdout.write(self.style.SUCCESS('Successfully generated AI context and dynamic floor.'))
            return (parsed.safety_floor_inr or DEFAULT_FLOOR), {i.symbol: i.context for i in parsed.items}
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Failed to generate AI context: {e}'))
            return DEFAULT_FLOOR, {}
