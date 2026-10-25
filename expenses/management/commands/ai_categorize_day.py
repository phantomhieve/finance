"""Management command to run Gemini AI categorization on daily expenses (intended for daily 2:00 AM cron)."""
from __future__ import annotations

import datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from expenses import ai
from expenses.categories import categories_by_name
from expenses.knowledge import record_ai_brand
from expenses.models import Expense, MerchantRule
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
        qs = Expense.objects.filter(group=group, is_deleted=False)
        if all_pending:
            qs = qs.filter(Q(category__isnull=True) | Q(category_source__in=('NONE', 'KEYWORD')))
            self.stdout.write(f"[{group.name}] Scanning all uncategorised/unconfirmed expenses...")
        elif target_date:
            qs = qs.filter(txn_date=target_date).filter(Q(category__isnull=True) | Q(category_source__in=('NONE', 'KEYWORD')))
            self.stdout.write(f"[{group.name}] Scanning expenses for {target_date}...")

        pending = list(qs.order_by('-txn_date', '-id'))
        if not pending:
            self.stdout.write(self.style.SUCCESS(f"[{group.name}] No pending transactions to categorise."))
            return

        self.stdout.write(f"[{group.name}] Found {len(pending)} transactions to evaluate with AI.")
        cats = categories_by_name(group)
        examples = list(
            MerchantRule.objects.filter(group=group, source='USER').select_related('category')
            .order_by('-updated_at').values_list('merchant_label', 'category__name')[:40]
        )

        by_key: dict[str, list[Expense]] = {}
        items: list[dict[str, Any]] = []

        for e in pending:
            bucket_key = e.merchant_key or f'#{e.pk}'
            if bucket_key in by_key:
                by_key[bucket_key].append(e)
                continue
            by_key[bucket_key] = [e]
            items.append({
                'id': e.pk,
                'merchant': e.merchant or e.merchant_raw or '(unknown)',
                'raw': e.merchant_raw,
                'amount': float(e.amount),
                'direction': e.direction,
                'channel': e.channel,
            })

        answers = ai.categorise(items, list(cats), [list(x) for x in examples])
        updated = 0
        for item in items:
            answer = answers.get(item['id'])
            if not answer:
                continue
            name, confidence = answer
            if name not in cats:
                continue
            lead = next(e for e in pending if e.pk == item['id'])
            group_rows = by_key[lead.merchant_key or f'#{lead.pk}']
            for e in group_rows:
                e.category = cats[name]
                e.category_source = 'AI'
                e.category_confidence = confidence
                e.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])
                updated += 1
            if lead.merchant_key and confidence >= 0.6:
                MerchantRule.objects.get_or_create(
                    group=group,
                    merchant_key=lead.merchant_key,
                    defaults={'category': cats[name], 'source': 'AI', 'merchant_label': lead.merchant},
                )
                record_ai_brand(
                    merchant_key=lead.merchant_key,
                    display_name=lead.merchant or lead.merchant_raw,
                    category_name=name,
                    confidence=confidence,
                )

        self.stdout.write(self.style.SUCCESS(f"[{group.name}] Successfully categorised {updated} transactions."))
