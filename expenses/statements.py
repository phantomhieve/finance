"""Credit-card statements: read PDFs, reconcile line items against alerts, track due dates."""
import datetime
import difflib
import io
import logging
from decimal import Decimal

from django.db import transaction

from . import ai, crypto
from .models import CardStatement, Expense, PaymentSource, StatementLine
from .parsing import (
    ParsedLine, ParsedTransaction, normalize_merchant, parse_date, parse_statement_lines,
    parse_statement_summary, to_decimal,
)

logger = logging.getLogger(__name__)

DATE_TOLERANCE_DAYS = 3
AMOUNT_TOLERANCE = Decimal('1.00')
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_PDF_TEXT = 400_000
REMINDER_DAYS = (5, 1, 0)


class PdfPasswordRequired(Exception):
    pass


def pdf_text(data, password=''):
    """Extract text from a (possibly encrypted) PDF. Raises PdfPasswordRequired."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        if not password or not reader.decrypt(password):
            raise PdfPasswordRequired()
    # Card statements are a few pages; the cap stops a hostile PDF from pinning a worker.
    pages = list(reader.pages)[:MAX_PDF_PAGES]
    return '\n'.join(page.extract_text() or '' for page in pages)[:MAX_PDF_TEXT]


def find_card(group, institution, last4):
    qs = PaymentSource.objects.filter(group=group, kind='CREDIT_CARD')
    if last4:
        card = qs.filter(last4=last4).first()
        if card:
            return card
    if institution:
        cards = list(qs.filter(institution=institution))
        if len(cards) == 1:
            return cards[0]
    return None


def get_or_create_card(group, institution, last4, owner=None):
    card = find_card(group, institution, last4)
    if card:
        return card
    return PaymentSource.objects.create(group=group, kind='CREDIT_CARD', institution=institution or '',
                                        last4=last4 or '', owner=owner, is_auto=True)


def _apply_summary(statement, summary):
    for field in ('statement_date', 'due_date', 'total_due', 'min_due', 'period_start', 'period_end'):
        value = getattr(summary, field)
        if value is not None and getattr(statement, field) is None:
            setattr(statement, field, value)


def _lines_from_text(text):
    lines = parse_statement_lines(text)
    if lines:
        return lines
    out = []
    for row in ai.extract_statement_lines(text):
        d = parse_date(row.date)
        amount = to_decimal(row.amount)
        if d and amount:
            out.append(ParsedLine(txn_date=d, description=row.description[:255], amount=abs(amount),
                                  is_credit=row.is_credit))
    return out


def read_pdf(statement, data, password=''):
    """Parse a statement PDF into lines + totals. Keeps the PDF if a password is needed."""
    password = password or statement.payment_source.statement_password
    try:
        text = pdf_text(data, password)
    except PdfPasswordRequired:
        statement.pdf_blob = crypto.encrypt_bytes(data)
        statement.status = 'NEEDS_PASSWORD'
        statement.save()
        return statement
    except Exception:
        logger.exception('Could not read statement PDF %s', statement.pk)
        statement.status = 'FAILED'
        statement.save()
        return statement

    _apply_summary(statement, parse_statement_summary('', '', text))
    lines = _lines_from_text(text)
    with transaction.atomic():
        statement.lines.all().delete()
        StatementLine.objects.bulk_create([
            StatementLine(statement=statement, txn_date=ln.txn_date, description=ln.description,
                          amount=ln.amount, is_credit=ln.is_credit)
            for ln in lines
        ])
        statement.line_count = len(lines)
        statement.status = 'PARSED' if lines else 'FAILED'
        statement.pdf_blob = None
        statement.save()
    if lines:
        reconcile(statement)
    return statement


def _period(statement):
    lines = list(statement.lines.all())
    if statement.period_start and statement.period_end:
        return statement.period_start, statement.period_end
    if lines:
        return min(ln.txn_date for ln in lines), max(ln.txn_date for ln in lines)
    end = statement.statement_date or statement.created_at.date()
    return end - datetime.timedelta(days=31), end


def _best_match(line, candidates, used):
    best, best_score = None, -1.0
    _, line_key = normalize_merchant(line.description)
    for e in candidates:
        if e.pk in used:
            continue
        if abs(e.amount - line.amount) > AMOUNT_TOLERANCE:
            continue
        gap = abs((e.txn_date - line.txn_date).days)
        if gap > DATE_TOLERANCE_DAYS:
            continue
        similarity = difflib.SequenceMatcher(None, line_key, e.merchant_key or '').ratio() if line_key else 0
        score = similarity + (1 - gap / (DATE_TOLERANCE_DAYS + 1)) + (1 if e.amount == line.amount else 0)
        if score > best_score:
            best, best_score = e, score
    return best


@transaction.atomic
def reconcile(statement):
    """Match statement lines to alert-based expenses; add the ones no alert ever reported."""
    from .anomaly import apply_flags
    from .services import build_expense, categories_by_name

    start, end = _period(statement)
    card = statement.payment_source
    candidates = list(
        Expense.objects.filter(
            group=statement.group, is_deleted=False,
            txn_date__gte=start - datetime.timedelta(days=DATE_TOLERANCE_DAYS),
            txn_date__lte=end + datetime.timedelta(days=DATE_TOLERANCE_DAYS),
        ).filter(payment_source=card).exclude(source='STATEMENT')
    )
    already = set(StatementLine.objects.filter(statement__group=statement.group, matched_expense__isnull=False)
                  .exclude(statement=statement).values_list('matched_expense_id', flat=True))
    used = set(already)
    cats = categories_by_name(statement.group)
    matched = added = 0

    for idx, line in enumerate(statement.lines.all()):
        if line.is_credit and _is_payment(line.description):
            continue
        direction = 'CREDIT' if line.is_credit else 'DEBIT'
        match = _best_match(line, [c for c in candidates if c.direction == direction], used)
        if match:
            used.add(match.pk)
            line.matched_expense = match
            line.was_added = False
            line.save(update_fields=['matched_expense', 'was_added'])
            matched += 1
            continue
        display, key = normalize_merchant(line.description)
        parsed = ParsedTransaction(
            amount=line.amount, direction=direction, txn_date=line.txn_date, merchant=display or line.description,
            merchant_raw=line.description, merchant_key=key, instrument='CREDIT_CARD', channel='CARD',
            institution=card.institution, last4=card.last4,
        )
        expense, created = build_expense(
            statement.group, parsed, source='STATEMENT', member=card.owner, statement=statement,
            dedupe_key=f'st:{statement.pk}:{idx}', cats=cats,
        )
        if created:
            expense.payment_source = card
            expense.notes = 'Found on card statement — no email alert was received'
            expense.save(update_fields=['payment_source', 'notes'])
            apply_flags(expense)
        line.matched_expense = expense
        line.was_added = True
        line.save(update_fields=['matched_expense', 'was_added'])
        added += created

    statement.matched_count = matched
    statement.added_count = statement.lines.filter(was_added=True).count()
    statement.line_count = statement.lines.count()
    statement.save(update_fields=['matched_count', 'added_count', 'line_count'])
    return matched, added


def _is_payment(description):
    d = description.lower()
    return any(w in d for w in ('payment received', 'thank you', 'payment - ', 'bbps payment', 'autopay', 'neft payment'))


def ingest_statement_email(group, account, message_id, sender, subject, body, pdfs, fetch_pdf):
    """Create a CardStatement from a statement email. fetch_pdf(descriptor) -> bytes."""
    summary = parse_statement_summary(sender, subject, body)
    card = get_or_create_card(group, summary.institution, summary.last4, owner=account.user)
    statement, created = CardStatement.objects.get_or_create(
        group=group, gmail_message_id=message_id,
        defaults={'payment_source': card, 'gmail_account': account},
    )
    if not created:
        return statement
    _apply_summary(statement, summary)
    statement.save()
    for pdf in pdfs[:1]:
        try:
            data = fetch_pdf(pdf)
        except Exception:
            logger.exception('Could not download statement PDF for %s', message_id)
            continue
        if data and len(data) <= MAX_PDF_BYTES:
            read_pdf(statement, data)
    return statement


def record_card_payment(group, amount, last4, institution, paid_on):
    """Mark the latest unpaid statement of the card as paid when a payment-received email arrives."""
    card = find_card(group, institution, last4)
    if not card or not amount:
        return None
    statement = (CardStatement.objects.filter(group=group, payment_source=card, is_paid=False)
                 .order_by('-statement_date', '-created_at').first())
    if not statement:
        return None
    threshold = statement.min_due or statement.total_due or Decimal('0')
    if amount >= threshold:
        statement.is_paid = True
        statement.paid_at = paid_on
        statement.paid_amount = amount
        statement.save(update_fields=['is_paid', 'paid_at', 'paid_amount'])
    return statement


def due_reminders(group, today=None):
    """Unpaid statements due within the reminder window that haven't been reminded today."""
    today = today or datetime.date.today()
    out = []
    for st in (CardStatement.objects.filter(group=group, is_paid=False, due_date__isnull=False,
                                            due_date__gte=today - datetime.timedelta(days=3))
               .select_related('payment_source')):
        days_left = (st.due_date - today).days
        if days_left in REMINDER_DAYS or days_left < 0:
            if st.reminder_sent_on != today:
                out.append((st, days_left))
    return out


def upcoming_dues(group, today=None, horizon_days=21):
    today = today or datetime.date.today()
    return list(
        CardStatement.objects.filter(
            group=group, is_paid=False, due_date__isnull=False,
            due_date__gte=today - datetime.timedelta(days=7),
            due_date__lte=today + datetime.timedelta(days=horizon_days),
        ).select_related('payment_source').order_by('due_date')
    )
