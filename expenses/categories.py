"""Expense category definitions, automated rule resolution, and machine learning mappings."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from . import ai
from .knowledge import record_ai_brand
from .models import Expense, ExpenseCategory, MerchantRule
from .parsing import brand_category

if TYPE_CHECKING:
    from tracker.models import AccountGroup, User

logger = logging.getLogger(__name__)

def get_default_categories() -> list[tuple[str, str, str, int]]:
    """Return default category specifications loaded from CategoryTemplate in database."""
    from .knowledge import get_category_templates

    return get_category_templates()


class _DefaultCategoriesProxy(list):
    """Backwards-compatible dynamic list proxy that retrieves categories from CategoryTemplate in database."""

    def __iter__(self):
        return iter(get_default_categories())

    def __len__(self):
        return len(get_default_categories())

    def __getitem__(self, idx):
        return get_default_categories()[idx]


# Dynamic list proxy so external references (e.g. services.py) pull directly from DB
DEFAULT_CATEGORIES = _DefaultCategoriesProxy()


def ensure_default_categories(group: AccountGroup) -> None:
    """Ensure standard system categories exist for this household group from CategoryTemplate in database."""
    from .knowledge import ensure_seed_knowledge
    from .models import CategoryTemplate

    ensure_seed_knowledge()
    templates = list(CategoryTemplate.objects.all().order_by('sort_order', 'id'))
    existing = set(ExpenseCategory.objects.filter(group=group).values_list('name', flat=True))
    missing = [
        ExpenseCategory(
            group=group,
            name=t.name,
            kind=t.kind,
            icon=t.icon,
            hue=t.hue,
            sort_order=t.sort_order,
        )
        for t in templates
        if t.name not in existing
    ]
    if missing:
        ExpenseCategory.objects.bulk_create(missing, ignore_conflicts=True)


def categories_by_name(group: AccountGroup) -> dict[str, ExpenseCategory]:
    """Return map of category name -> ExpenseCategory model instance."""
    ensure_default_categories(group)
    return {c.name: c for c in ExpenseCategory.objects.filter(group=group)}


def _rule_for(group: AccountGroup, merchant_key: str) -> MerchantRule | None:
    if not merchant_key:
        return None
    return MerchantRule.objects.select_related('category').filter(group=group, merchant_key=merchant_key).first()


def categorise_expense(expense: Expense, cats: dict[str, ExpenseCategory] | None = None) -> None:
    """Assign a category without AI: learned rule → built-in brand/keyword → income default.

    Leaves category None (source NONE) when nothing matches so the AI batch can pick it up.
    """
    cats = cats or categories_by_name(expense.group)
    rule = _rule_for(expense.group, expense.merchant_key)
    if rule:
        expense.category = rule.category
        expense.category_source = 'RULE' if rule.source == 'USER' else 'AI'
        expense.category_confidence = 1.0 if rule.source == 'USER' else None
        MerchantRule.objects.filter(pk=rule.pk).update(hits=rule.hits + 1)
        return

    name = brand_category(expense.merchant_key, f'{expense.merchant} {expense.merchant_raw}')
    if not name and expense.channel == 'ATM':
        name = 'Cash Withdrawal'
    if not name and expense.direction == 'CREDIT':
        combined = f'{expense.merchant} {expense.merchant_raw} {expense.email_subject} {expense.notes}'.lower()
        is_refund_kw = any(kw in combined for kw in ('refund', 'reversal', 'cashback', 'return', 'reversed'))
        if expense.payment_source and expense.payment_source.kind == 'CREDIT_CARD' and not is_refund_kw:
            name = 'Credit Card Payment'
            if not expense.merchant or expense.merchant in ('Unknown merchant', 'Unknown'):
                expense.merchant = 'Credit Card Bill Payment'
        elif any(kw in combined for kw in ('credit card bill', 'card payment', 'bill payment', 'payment received', 'auto-debit', 'autopay', 'vpa club@axisb', 'cred')):
            name = 'Credit Card Payment'
            if not expense.merchant or expense.merchant in ('Unknown merchant', 'Unknown'):
                expense.merchant = 'Credit Card Bill Payment'
        else:
            name = 'Income & Refunds'

    if name and name in cats:
        expense.category = cats[name]
        expense.category_source = 'KEYWORD'
        expense.category_confidence = 0.7


def ai_categorise_pending(group: AccountGroup, limit: int = 200) -> int:
    """Ask Gemini to categorise uncategorised rows; cache confident answers as AI rules."""
    pending = list(
        Expense.objects.filter(group=group, is_deleted=False, category__isnull=True, category_source='NONE')
        .order_by('-txn_date')[:limit]
    )
    if not pending or not ai.ai_available():
        return 0

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
    return updated


@transaction.atomic
def learn_category(expense: Expense, category: ExpenseCategory, user: User, apply_to_similar: bool = False) -> int:
    """User picked a category: remember it for this merchant and re-file past non-user rows."""
    expense.category = category
    expense.category_source = 'USER'
    expense.category_confidence = 1.0
    expense.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])
    if not expense.merchant_key or not apply_to_similar:
        return 0

    record_ai_brand(
        merchant_key=expense.merchant_key,
        display_name=expense.merchant or expense.merchant_key,
        category_name=category.name,
        confidence=1.0,
    )
    MerchantRule.objects.update_or_create(
        group=expense.group,
        merchant_key=expense.merchant_key,
        defaults={
            'category': category,
            'source': 'USER',
            'created_by': user,
            'merchant_label': expense.merchant or expense.merchant_key,
        },
    )
    return (
        Expense.objects.filter(group=expense.group, merchant_key=expense.merchant_key)
        .exclude(pk=expense.pk)
        .exclude(category_source__in=('USER', 'MATCH'))
        .update(category=category, category_source='RULE', category_confidence=1.0)
    )
