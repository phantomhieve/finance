"""Pull bank/card emails from connected Gmail accounts and turn them into expenses."""
import datetime
import logging
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

from django.db import IntegrityError
from django.utils import timezone

from . import ai
from .anomaly import ai_detect_anomalies_for_expenses
from .gmail import GmailAuthError, GmailClient, GmailError, decode_body, message_parts
from .models import CardStatement, Expense, GmailAccount, ProcessedEmail
from .parsing import (
    ParsedTransaction, classify, looks_like_card_statement, mask_sensitive, normalize_merchant,
    parse_card_payment, parse_date, parse_transaction, to_decimal,
)
from .services import ai_categorise_pending, build_expense, categories_by_name, settle_internal_movements
from .statements import ingest_statement_email, record_card_payment, retry_locked_statements

logger = logging.getLogger(__name__)

# Content-based so it keeps working as banks move sender domains (e.g. to *.bank.in).
GMAIL_QUERY = (
    '{subject:(debited OR credited OR spent OR transaction OR txn OR alert OR "credit card" OR statement '
    'OR payment OR UPI OR purchase OR withdrawal) '
    '"has been debited" "has been credited" "spent on your" "is debited" "is credited"} '
    '-category:social -category:promotions -in:chats'
)
OVERLAP_HOURS = 48
MAX_MESSAGES = 500
# Statement emails only — used to back-fill months the incremental sync never looked at.
STATEMENT_QUERY = (
    '{subject:statement subject:e-statement subject:estatement} has:attachment filename:pdf '
    '-category:social -category:promotions -in:chats'
)
BACKFILL_MAX_MESSAGES = 300


@dataclass
class SyncResult:
    fetched: int = 0
    transactions: int = 0
    statements: int = 0
    payments: int = 0
    ignored: int = 0
    errors: int = 0
    complete: bool = True
    error: str = ''
    new_expense_ids: list = field(default_factory=list)


def _received_at(headers, message):
    try:
        return parsedate_to_datetime(headers.get('date', ''))
    except (TypeError, ValueError):
        ms = int(message.get('internalDate', 0) or 0)
        return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc) if ms else timezone.now()


def _ai_parsed(subject, body, received_date):
    found = ai.extract_transaction(subject, body)
    if not found:
        return None
    amount = to_decimal(found.amount)
    if not amount or amount <= 0:
        return None
    display, key = normalize_merchant(found.merchant or '')
    instrument = found.instrument if found.instrument in ('CREDIT_CARD', 'DEBIT_CARD', 'BANK_ACCOUNT', 'UPI') else 'OTHER'
    return ParsedTransaction(
        amount=amount, direction='CREDIT' if (found.direction or '').upper() == 'CREDIT' else 'DEBIT',
        txn_date=parse_date(found.date or '', received_date) or received_date,
        merchant=display, merchant_raw=(found.merchant or '')[:255], merchant_key=key,
        currency=(found.currency or 'INR').upper()[:3], instrument=instrument,
        channel='CARD' if instrument in ('CREDIT_CARD', 'DEBIT_CARD') else ('UPI' if instrument == 'UPI' else 'OTHER'),
        last4=(found.last4 or '')[-4:],
    )


def ingest_email(account, message_id, sender, subject, body, received_at, pdfs=(), fetch_pdf=None, cats=None):
    """Process one email. Returns (kind, expense_or_None). Idempotent per (account, message_id)."""
    group = account.group
    if ProcessedEmail.objects.filter(gmail_account=account, message_id=message_id).exists():
        return 'SEEN', None

    kind = classify(sender, subject, body)
    if kind != 'STATEMENT' and looks_like_card_statement(subject, body, bool(pdfs)):
        kind = 'STATEMENT'
    expense = None
    received_date = timezone.localtime(received_at).date() if timezone.is_aware(received_at) else received_at.date()

    if kind == 'STATEMENT':
        ingest_statement_email(group, account, message_id, sender, subject, body, list(pdfs),
                               fetch_pdf or (lambda _pdf: b''))
    elif kind == 'CARD_PAYMENT':
        amount, last4, institution = parse_card_payment(sender, subject, body)
        record_card_payment(group, amount, last4, institution, received_date)
    elif kind == 'TXN':
        parsed = parse_transaction(sender, subject, body, received_at)
        if parsed and not parsed.merchant:
            parsed = _ai_parsed(subject, body, received_date) or parsed
        if not parsed:
            # Fall back to AI extraction if deterministic rules missed custom alert formatting
            parsed = _ai_parsed(subject, body, received_date)
        if parsed:
            expense, _ = build_expense(
                group, parsed, source='EMAIL', member=account.user, gmail_account=account,
                message_id=message_id, subject=subject, dedupe_key=f'gm:{message_id}', cats=cats,
            )
        else:
            kind = 'ERROR'

    try:
        ProcessedEmail.objects.create(gmail_account=account, message_id=message_id, kind=kind if kind != 'SEEN' else 'IGNORED',
                                      subject=mask_sensitive(subject)[:255])
    except IntegrityError:
        pass
    return kind, expense


def sync_account(account, time_budget=None, max_messages=MAX_MESSAGES):
    """Sync one mailbox. Newest first; stops early (complete=False) when the time budget runs out."""
    result = SyncResult()
    started = time.monotonic()
    started_at = timezone.now()
    if account.last_synced_at:
        since = account.last_synced_at - datetime.timedelta(hours=OVERLAP_HOURS)
    else:
        since = started_at - datetime.timedelta(days=account.backfill_days)
    query = f'{GMAIL_QUERY} after:{int(since.timestamp())}'

    client = GmailClient(account.refresh_token)
    try:
        ids = client.list_message_ids(query, limit=max_messages)
        seen = set(ProcessedEmail.objects.filter(gmail_account=account, message_id__in=ids)
                   .values_list('message_id', flat=True))
        todo = [i for i in ids if i not in seen]
        cats = categories_by_name(account.group)
        for message_id in todo:
            if time_budget and time.monotonic() - started > time_budget:
                result.complete = False
                break
            try:
                message = client.get_message(message_id)
                headers, body, pdfs = message_parts(message)
                kind, expense = ingest_email(
                    account, message_id, headers.get('from', ''), headers.get('subject', ''), body,
                    _received_at(headers, message), pdfs,
                    lambda pdf, mid=message_id: client.get_attachment(mid, pdf['attachment_id'])
                    if pdf.get('attachment_id') else decode_body(pdf.get('data') or ''),
                    cats,
                )
            except GmailAuthError:
                raise
            except Exception:
                logger.exception('Failed to ingest Gmail message for account %s', account.pk)
                result.errors += 1
                continue
            result.fetched += 1
            if kind == 'TXN' and expense:
                result.transactions += 1
                result.new_expense_ids.append(expense.pk)
            elif kind == 'STATEMENT':
                result.statements += 1
            elif kind == 'CARD_PAYMENT':
                result.payments += 1
            else:
                result.ignored += 1
    except GmailAuthError as exc:
        account.is_active = False
        account.last_error = str(exc)[:500]
        account.save(update_fields=['is_active', 'last_error'])
        result.error, result.complete = str(exc), False
        return result
    except GmailError as exc:
        account.last_error = str(exc)[:500]
        account.save(update_fields=['last_error'])
        result.error, result.complete = str(exc), False
        return result

    if result.new_expense_ids or result.statements or result.payments:
        _post_ingest(account.group, since.date(), result.new_expense_ids)
    else:
        retry_locked_statements(account.group)

    account.last_sync_new = result.transactions
    account.last_error = ''
    if result.complete:
        account.last_synced_at = started_at
    account.save(update_fields=['last_synced_at', 'last_sync_new', 'last_error'])
    return result


def _post_ingest(group, since_date, new_expense_ids=()):
    """Shared tail of every ingest: unlock PDFs, categorise, settle transfers, flag anomalies."""
    if isinstance(since_date, datetime.datetime):
        since_date = since_date.date()
    retry_locked_statements(group)
    ai_categorise_pending(group)
    settled = settle_internal_movements(group, since_date)
    affected = list(
        Expense.objects.filter(pk__in=set(new_expense_ids) | set(settled))
        .select_related('category', 'payment_source')
    )
    if affected:
        ai_detect_anomalies_for_expenses(affected, group=group)


@dataclass
class BackfillResult:
    scanned: int = 0
    statements: int = 0
    parsed: int = 0
    duplicates: int = 0
    locked: int = 0
    lines_added: int = 0
    lines_review: int = 0
    errors: int = 0
    complete: bool = True
    error: str = ''


def backfill_statements(account, since, time_budget=None, max_messages=BACKFILL_MAX_MESSAGES):
    """Re-scan a mailbox for card statements since `since` (a date), ignoring the sync cursor.

    Safe to repeat: statements are keyed by Gmail message id, duplicate cycles are detected, and
    reconciliation only adds lines that no recorded expense accounts for.
    """
    result = BackfillResult()
    started = time.monotonic()
    group = account.group
    after = int(datetime.datetime.combine(since, datetime.time.min, tzinfo=datetime.timezone.utc).timestamp())
    client = GmailClient(account.refresh_token)
    try:
        ids = client.list_message_ids(f'{STATEMENT_QUERY} after:{after}', limit=max_messages)
        known = set(CardStatement.objects.filter(
            group=group, gmail_message_id__in=ids, status__in=('PARSED', 'DUPLICATE')
        ).values_list('gmail_message_id', flat=True))
        for message_id in ids:
            if message_id in known:
                continue
            if time_budget and time.monotonic() - started > time_budget:
                result.complete = False
                break
            result.scanned += 1
            try:
                message = client.get_message(message_id)
                headers, body, pdfs = message_parts(message)
                sender, subject = headers.get('from', ''), headers.get('subject', '')
                if not pdfs or (classify(sender, subject, body) != 'STATEMENT'
                                and not looks_like_card_statement(subject, body, True)):
                    continue
                statement = ingest_statement_email(
                    group, account, message_id, sender, subject, body, list(pdfs),
                    lambda pdf, mid=message_id: client.get_attachment(mid, pdf['attachment_id'])
                    if pdf.get('attachment_id') else decode_body(pdf.get('data') or ''),
                )
            except GmailAuthError:
                raise
            except Exception:
                logger.exception('Statement backfill failed for a message in account %s', account.pk)
                result.errors += 1
                continue
            ProcessedEmail.objects.update_or_create(
                gmail_account=account, message_id=message_id,
                defaults={'kind': 'STATEMENT', 'subject': mask_sensitive(subject)[:255]},
            )
            result.statements += 1
            result.parsed += statement.status == 'PARSED'
            result.duplicates += statement.status == 'DUPLICATE'
            result.locked += statement.status == 'NEEDS_PASSWORD'
            result.lines_added += statement.added_count
            result.lines_review += statement.review_count
    except GmailAuthError as exc:
        account.is_active = False
        account.last_error = str(exc)[:500]
        account.save(update_fields=['is_active', 'last_error'])
        result.error, result.complete = str(exc), False
        return result
    except GmailError as exc:
        account.last_error = str(exc)[:500]
        account.save(update_fields=['last_error'])
        result.error, result.complete = str(exc), False
        return result

    if result.statements:
        _post_ingest(group, since)
    return result


def sync_group(group, time_budget=None):
    results = {}
    for account in GmailAccount.objects.filter(group=group, is_active=True):
        results[account.email] = sync_account(account, time_budget=time_budget)
    return results
