import json
import logging
import os
import sys
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from portfolio.ai import call_shakti, _clean_json_text, PortfolioInsightsResponse
from tracker.models import AccountGroup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test Shakti Cloud connectivity, stream raw test completions, or run a financial score calculation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--prompt',
            type=str,
            default=None,
            help="Custom test prompt to ping Shakti Cloud (e.g. 'what is 2+2?').",
        )
        parser.add_argument(
            '--group',
            type=str,
            default=None,
            help="AccountGroup name or ID to test financial score calculation with real data.",
        )
        parser.add_argument(
            '--benchmark',
            action='store_true',
            help="Run financial score calculation using built-in synthetic benchmark portfolio data.",
        )

    def handle(self, *args, **options):
        api_key = os.environ.get('SHAKTI_API_KEY') or getattr(settings, 'SHAKTI_API_KEY', '')
        base_url = (
            os.environ.get('SHAKTI_BASE_URL')
            or getattr(settings, 'SHAKTI_BASE_URL', 'https://http.prod-llm.shaktistudio.shakticloud.ai')
        ).strip().rstrip('/')
        client_id = (
            os.environ.get('SHAKTI_CLIENT_ID')
            or getattr(settings, 'SHAKTI_CLIENT_ID', '')
        )
        model = os.environ.get('SHAKTI_MODEL') or getattr(settings, 'SHAKTI_MODEL', 'llama3_3')

        self.stdout.write(self.style.MIGRATE_HEADING("=== Shakti Cloud Configuration ==="))
        self.stdout.write(f"Base URL:     {base_url}")
        self.stdout.write(f"Client ID:    {client_id}")
        self.stdout.write(f"Model:        {model}")
        self.stdout.write(f"API Key:      {'[Configured - ' + api_key[:4] + '...' + api_key[-4:] + ']' if api_key and len(api_key) > 8 else ('[Set]' if api_key else '[MISSING - Set SHAKTI_API_KEY in .env]')}")
        self.stdout.write(f"Active Provider: {getattr(settings, 'AI_PROVIDER', 'not set')}")

        if not api_key:
            self.stdout.write(self.style.ERROR(
                "\nError: SHAKTI_API_KEY is not set. Please add SHAKTI_API_KEY=<your_key> to your .env file."
            ))
            sys.exit(1)

        custom_prompt = options.get('prompt')
        if custom_prompt:
            self._test_raw_prompt(api_key, base_url, client_id, model, custom_prompt)
            return

        # Score calculation test
        group_query = options.get('group')
        use_benchmark = options.get('benchmark')
        group = None

        if group_query:
            if group_query.isdigit():
                group = AccountGroup.objects.filter(id=int(group_query)).first()
            else:
                group = AccountGroup.objects.filter(name__icontains=group_query).first()
            if not group:
                self.stdout.write(self.style.WARNING(f"AccountGroup '{group_query}' not found. Using default/benchmark."))

        if not group and not use_benchmark:
            group = AccountGroup.objects.first()

        if group and not use_benchmark:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Calculating Financial Score for Group: {group.name} ==="))
            from portfolio.services import get_portfolio_summary, get_growth_data
            from portfolio.ai import build_prompt_data

            summary = get_portfolio_summary(group)
            growth = get_growth_data(group=group)
            prompt_data = build_prompt_data(summary, growth, group)
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Calculating Financial Score with Benchmark Portfolio ==="))
            prompt_data = self._benchmark_portfolio_data()

        self.stdout.write("Dispatching portfolio data to Shakti Cloud...")
        try:
            result = call_shakti(prompt_data, group=group)
            self._display_score_results(result)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nFailed to calculate finance score via Shakti Cloud: {e}"))
            logger.exception("Shakti test failure")
            sys.exit(1)

    def _test_raw_prompt(self, api_key, base_url, client_id, model, prompt):
        from openai import OpenAI
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Pinging Shakti Cloud with prompt: '{prompt}' ==="))
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"id": client_id} if client_id else None,
            timeout=60.0,
        )
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                stream=True,
            )
            self.stdout.write(self.style.SUCCESS("Stream response started:\n"))
            for res in response:
                if res.choices and len(res.choices) > 0 and res.choices[0].delta:
                    content = res.choices[0].delta.content or ""
                    sys.stdout.write(content)
                    sys.stdout.flush()
            sys.stdout.write("\n\n")
            self.stdout.write(self.style.SUCCESS("Ping succeeded!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nPing failed: {e}"))
            sys.exit(1)

    def _display_score_results(self, result):
        ins = result.insights_dict
        score = ins.get('score', 0)
        score_style = self.style.SUCCESS if score >= 70 else (self.style.WARNING if score >= 50 else self.style.ERROR)

        self.stdout.write(self.style.SUCCESS(f"\nModel Used: {result.model}"))
        self.stdout.write(score_style(f"FINANCIAL HEALTH SCORE: {score}/100"))
        self.stdout.write("\nSummary:")
        self.stdout.write(f"  {ins.get('summary', 'N/A')}")

        if ins.get('market_context'):
            self.stdout.write("\nMarket Context:")
            self.stdout.write(f"  {ins.get('market_context')}")

        if ins.get('outlook'):
            self.stdout.write("\nOutlook (Next 3-6 Months):")
            self.stdout.write(f"  {ins.get('outlook')}")

        insights = ins.get('insights', [])
        self.stdout.write(f"\nGenerated Insights ({len(insights)}):")
        for i, item in enumerate(insights, 1):
            sev = item.get('severity', 'info').upper()
            cat = item.get('category', 'general').upper()
            title = item.get('title', '')
            detail = item.get('detail', '')
            action = item.get('action')

            sev_formatted = f"[{sev}]"
            self.stdout.write(f"  {i}. {sev_formatted} ({cat}) {title}")
            self.stdout.write(f"     Detail: {detail}")
            if action:
                self.stdout.write(f"     Action: -> {action}")

    def _benchmark_portfolio_data(self):
        return {
            "summary": {
                "total_value": 7500000.0,
                "total_invested": 5200000.0,
                "total_returns": 2300000.0,
                "return_pct": 44.23,
            },
            "asset_allocation": [
                {"name": "Indian Stocks", "value": 3000000.0, "pct": 40.0},
                {"name": "Mutual Funds", "value": 2000000.0, "pct": 26.67},
                {"name": "EPF / NPS", "value": 1200000.0, "pct": 16.0},
                {"name": "Gold / Silver", "value": 600000.0, "pct": 8.0},
                {"name": "Fixed Deposits & Cash", "value": 700000.0, "pct": 9.33},
            ],
            "stocks_consolidated": [
                {
                    "symbol": "HDFCBANK",
                    "total_invested": 600000.0,
                    "total_current": 750000.0,
                    "total_pnl": 150000.0,
                    "total_pnl_pct": 25.0,
                    "pct_of_portfolio": 10.0,
                },
                {
                    "symbol": "RELIANCE",
                    "total_invested": 500000.0,
                    "total_current": 700000.0,
                    "total_pnl": 200000.0,
                    "total_pnl_pct": 40.0,
                    "pct_of_portfolio": 9.33,
                },
            ],
            "mutual_funds_active_sip": [
                {"name": "Parag Parikh Flexi Cap Fund", "current_value": 1200000.0, "invested_value": 800000.0},
                {"name": "UTI Nifty 50 Index Fund", "current_value": 800000.0, "invested_value": 600000.0},
            ],
            "goals": [
                {"label": "Retirement Corpus", "target": 50000000.0, "current": 7500000.0, "progress_pct": 15.0},
            ],
        }
