"""Management command to run portfolio AI insights via the multi-stage DAG engine."""
from __future__ import annotations

import logging
import sys

from django.core.management.base import BaseCommand

from tracker.models import AccountGroup
from portfolio.models import PortfolioInsight
from portfolio.services import get_portfolio_summary, get_growth_data
from portfolio.ai import build_prompt_data, call_ai_insights

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run AI portfolio insights generation using the multi-stage DAG engine and save to database."

    def add_arguments(self, parser):
        parser.add_argument(
            '--group',
            type=str,
            default=None,
            help="AccountGroup name or ID (defaults to primary household).",
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help="Bypass cooldown checks and force new insight generation.",
        )
        parser.add_argument(
            '--no-save',
            action='store_true',
            help="Do not save the generated insight to the database.",
        )

    def handle(self, *args, **options):
        group_query = options.get('group')
        group = None

        if group_query:
            if group_query.isdigit():
                group = AccountGroup.objects.filter(id=int(group_query)).first()
            else:
                group = AccountGroup.objects.filter(name__icontains=group_query).first()
            if not group:
                self.stdout.write(self.style.WARNING(f"AccountGroup '{group_query}' not found. Falling back to default."))

        if not group:
            group = AccountGroup.objects.first()

        if not group:
            self.stdout.write(self.style.ERROR("Error: No AccountGroup found in database."))
            sys.exit(1)

        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Generating Portfolio Insights for: {group.name} ==="))
        self.stdout.write("1. Compiling portfolio summary and growth history...")

        summary = get_portfolio_summary(group)
        growth = get_growth_data(group=group)
        prompt_data = build_prompt_data(summary, growth, group)

        self.stdout.write(f"   Total Portfolio Value: Rs {float(summary['total_value']):,.2f}")
        self.stdout.write(f"   Holdings tracked: {len(prompt_data.get('stocks_all', []))} stocks, "
                          f"{len(prompt_data.get('mutual_funds_active_sip', []))} active MFs, "
                          f"{len(prompt_data.get('mutual_funds_legacy', []))} legacy MFs")

        self.stdout.write("2. Invoking AI Engine (Multi-Stage DAG / AI Gateway)...")
        try:
            result = call_ai_insights(prompt_data, group=group)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"AI insights execution failed: {e}"))
            logger.exception("AI generation failure")
            sys.exit(1)

        insights_dict = result.insights_dict or {}
        score = insights_dict.get('score', 'N/A')
        dag_meta = insights_dict.get('_dag_metadata')

        self.stdout.write(self.style.SUCCESS(f"\n=== Execution Complete (Engine: {result.model}) ==="))
        self.stdout.write(self.style.MIGRATE_HEADING(f"Financial Health Score: {score}/100"))

        if dag_meta:
            sub = dag_meta.get('sub_scores', {})
            self.stdout.write(
                f"   [Pillar Sub-Scores] "
                f"Allocation: {sub.get('allocation', 'N/A')} | "
                f"Quality: {sub.get('quality', 'N/A')} | "
                f"Strategy: {sub.get('strategy', 'N/A')} | "
                f"Macro: {sub.get('macro', 'N/A')}"
            )
            self.stdout.write(f"   [DAG Nodes Executed] {', '.join(dag_meta.get('nodes_executed', []))}")
            self.stdout.write(f"   [Execution Latency] {dag_meta.get('elapsed_ms', 0):.1f} ms")

        self.stdout.write("\n--- Executive Summary ---")
        self.stdout.write(insights_dict.get('summary', ''))

        if insights_dict.get('market_context'):
            self.stdout.write("\n--- Market Context ---")
            self.stdout.write(insights_dict.get('market_context', ''))

        if insights_dict.get('outlook'):
            self.stdout.write("\n--- Strategic Outlook ---")
            self.stdout.write(insights_dict.get('outlook', ''))

        insights_list = insights_dict.get('insights', [])
        if insights_list:
            self.stdout.write(f"\n--- Key Insights ({len(insights_list)}) ---")
            for idx, item in enumerate(insights_list, 1):
                sev = (item.get('severity') or 'info').upper()
                cat = (item.get('category') or 'general').upper()
                title = item.get('title', '')
                detail = item.get('detail', '')
                action = item.get('action')

                color = self.style.SUCCESS if sev == 'POSITIVE' else (
                    self.style.ERROR if sev == 'CRITICAL' else (
                        self.style.WARNING if sev == 'WARNING' else self.style.NOTICE
                    )
                )
                self.stdout.write(color(f"{idx}. [{sev}] [{cat}] {title}"))
                self.stdout.write(f"   {detail}")
                if action:
                    self.stdout.write(self.style.MIGRATE_LABEL(f"   Action: {action}"))

        if not options.get('no_save'):
            ins = PortfolioInsight.objects.create(
                group=group,
                model_used=result.model,
                prompt_data=prompt_data,
                insights=insights_dict,
            )
            self.stdout.write(self.style.SUCCESS(f"\n[Saved to database as PortfolioInsight #{ins.id}! Dashboard updated.]"))
        else:
            self.stdout.write(self.style.WARNING("\n[Insight generation not saved (--no-save specified)]"))
