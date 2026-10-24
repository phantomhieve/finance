"""Transaction ingestion pipeline, payment source resolution, and self-transfer reconciliation."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from .analytics import live
from .categories import categories_by_name, categorise_expense
from .models import CardStatement, Expense, ExpenseCategory, PaymentSource
from .parsing import ParsedTransaction, mask_sensitive, normalize_merchant

if TYPE_CHECKING:
    from tracker.models import AccountGroup, User

SETTLE_WINDOW_DAYS = 3


def resolve_payment_source(
    group: AccountGroup,
    instrument: str,
    institution: str,
    last4: str,
    owner: User | None = None,
) -> PaymentSource | None:
    """Find or auto-create a PaymentSource matching the instrument, bank, and last 4 digits."""
    if not (institution or last4):
        return None
    kind = instrument if instrument in dict(PaymentSource.KIND_CHOICES) else 'OTHER'
    source, _ = PaymentSource.objects.get_or_create(
        group=group,
        kind=kind,
        institution=institution or '',
        last4=last4 or '',
        defaults={'owner': owner, 'is_auto': True},
    )
    return source


def build_expense(
    group: AccountGroup,
    parsed: ParsedTransaction,
    *,
    source: str,
    member: User | None = None,
    gmail_account: Any = None,
    message_id: str = '',
    subject: str = '',
    dedupe_key: str = '',
    statement: CardStatement | None = None,
    cats: dict[str, ExpenseCategory] | None = None,
) -> tuple[Expense, bool]:
    """Create (and categorise) an Expense from a ParsedTransaction. Returns (expense, created)."""
    if dedupe_key:
        existing = Expense.objects.filter(group=group, dedupe_key=dedupe_key).first()
        if existing:
            return existing, False

    payment_source = resolve_payment_source(group, parsed.instrument, parsed.institution, parsed.last4, member)
    merchant = parsed.merchant
    if not merchant and parsed.channel == 'ATM':
        merchant = 'Cash withdrawal'

    expense = Expense(
        group=group,
        amount=parsed.amount,
        currency=parsed.currency,
        direction=parsed.direction,
        txn_date=parsed.txn_date,
        txn_time=parsed.txn_time,
        merchant=merchant or 'Unknown merchant',
        merchant_raw=parsed.merchant_raw[:255],
        merchant_key=parsed.merchant_key,
        payment_source=payment_source,
        channel=parsed.channel,
        reference=parsed.reference[:64],
        source=source,
        gmail_account=gmail_account,
        gmail_message_id=message_id,
        email_subject=mask_sensitive(subject or '')[:255],
        dedupe_key=dedupe_key,
        statement=statement,
        member=member or (payment_source.owner if payment_source else None),
    )
    categorise_expense(expense, cats)
    expense.save()
    return expense, True


def manual_merchant(expense: Expense) -> None:
    """Recompute display name and deduplication merchant key after a manual user edit."""
    display, key = normalize_merchant(expense.merchant)
    expense.merchant_key = key
    if not expense.merchant_raw:
        expense.merchant_raw = expense.merchant


def _statement_paid_by(statement: CardStatement, debit: Expense, window: datetime.timedelta) -> bool:
    if (
        statement.paid_amount is not None
        and abs(statement.paid_amount - debit.amount) <= Decimal('1.00')
        and statement.paid_at
        and abs((statement.paid_at - debit.txn_date).days) <= window.days
    ):
        return True
    issued = statement.statement_date or statement.created_at.date()
    due = statement.due_date or issued + datetime.timedelta(days=20)
    return (
        statement.total_due is not None
        and abs(statement.total_due - debit.amount) <= Decimal('1.00')
        and issued - window <= debit.txn_date <= due + window
    )


@transaction.atomic
def settle_internal_movements(group: AccountGroup, since: datetime.date) -> list[int]:
    """Re-file money that only moved between the household's own accounts, so it is never counted as spend.

    - A bank debit equal to a card statement's paid / total amount is that card's bill payment
      (the purchases on the card are already counted);
    - A debit matched by an equal credit into another of the household's accounts is a self-transfer.
    Returns the primary keys of re-filed debits.
    """
    cats = categories_by_name(group)
    bill, transfer = cats.get('Credit Card Payment'), cats.get('Transfers')
    window = datetime.timedelta(days=SETTLE_WINDOW_DAYS)
    open_rows = (
        live(group)
        .filter(txn_date__gte=since - window, currency='INR')
        .exclude(source='MANUAL')
        .exclude(category_source__in=('USER', 'MATCH'))
    )
    debits = list(open_rows.filter(direction='DEBIT').exclude(payment_source__kind='CREDIT_CARD'))
    if not debits:
        return []

    statements = list(
        CardStatement.objects.filter(group=group, created_at__date__gte=since - datetime.timedelta(days=60))
        .exclude(status='DUPLICATE')
    )
    credits = list(open_rows.filter(direction='CREDIT', payment_source__isnull=False))
    settled: list[int] = []
    used_credits: set[int] = set()

    def refile(expense: Expense, category: ExpenseCategory) -> None:
        expense.category = category
        expense.category_source = 'MATCH'
        expense.category_confidence = 1.0
        expense.save(update_fields=['category', 'category_source', 'category_confidence', 'updated_at'])

    for debit in debits:
        if bill and any(_statement_paid_by(st, debit, window) for st in statements):
            refile(debit, bill)
            settled.append(debit.pk)
            continue
        if not transfer or not debit.payment_source_id:
            continue
        twin = next(
            (
                c for c in credits
                if c.pk not in used_credits
                and c.amount == debit.amount
                and c.payment_source_id != debit.payment_source_id
                and abs((c.txn_date - debit.txn_date).days) <= 1
            ),
            None,
        )
        if twin:
            used_credits.add(twin.pk)
            refile(debit, transfer)
            refile(twin, transfer)
            settled.append(debit.pk)

    return settled
