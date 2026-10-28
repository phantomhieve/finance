"""Credit-card statements: read PDFs, reconcile line items against alerts, track due dates.

Back-filling a month from its statement must never double count, so reconciliation is staged:

1. Rule match: same card (or a variant of it), amount within ₹1, date within 3 days, unambiguous.
2. AI match: lines left over that still have *plausible* candidates (renamed merchants, late
   postings, foreign-currency alerts, manual entries without a card) go to the model. A confident
   "same transaction" links them; a confident "new" adds them; anything uncertain is parked for
   review rather than risking a duplicate.
3. Lines with no plausible candidate at all are added straight away.

Statements themselves are de-duplicated by PDF hash, billing period and line overlap, so a
statement that arrives by email *and* is uploaded by hand is only reconciled once.
"""
import datetime
import difflib
import hashlib
import io
import logging
import re
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

from . import ai, crypto
from .models import CardStatement, Expense, PaymentSource, StatementLine
from .parsing import (
    ParsedLine, ParsedTransaction, normalize_merchant, parse_date, parse_emi_details,
    parse_statement_lines, parse_statement_summary, to_decimal,
)

logger = logging.getLogger(__name__)

DATE_TOLERANCE_DAYS = 3
AMOUNT_TOLERANCE = Decimal('1.00')
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_PDF_TEXT = 400_000
MAX_PDFS_PER_EMAIL = 3
REMINDER_DAYS = (5, 1, 0)

# Rule stage: accept the best candidate only when it is clearly the one.
RULE_SIMILARITY = 0.55
RULE_MARGIN = 0.25
SINGLE_CANDIDATE_SIMILARITY = 0.3
# AI stage: what counts as a plausible duplicate worth asking about.
LOOSE_DATE_DAYS = 10
LOOSE_AMOUNT_RATIO = Decimal('0.06')
MAX_AI_CANDIDATES = 5
AI_MATCH_CONFIDENCE = 0.8
AI_NEW_CONFIDENCE = 0.7
# Extraction / statement de-duplication.
REGEX_COVERAGE = 0.8
DUPLICATE_LINE_SHARE = 0.8

_DATE_LED_ROW = re.compile(r'^\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s?[A-Za-z]{3}\s?\d{2,4})\b')
_LINE_FIELDS = ['matched_expense', 'was_added', 'match_method', 'match_confidence', 'needs_review',
                'suggested_expense', 'match_reason']


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
        card = qs.filter(institution=institution, last4='').first()
        if card:
            return card
        cards = list(qs.filter(institution=institution))
        if len(cards) == 1:
            return cards[0]
    return None


def get_or_create_card(group, institution, last4, owner=None):
    card = find_card(group, institution, last4)
    if card:
        return card
    card, _ = PaymentSource.objects.get_or_create(
        group=group, kind='CREDIT_CARD', institution=institution or '', last4=last4 or '',
        defaults={'owner': owner, 'is_auto': True},
    )
    return card


def card_family_ids(card):
    """PaymentSource ids that may be this same physical card.

    Alerts and statements spell banks differently and some alerts omit the last 4 digits, so the
    same card can end up as several PaymentSource rows. Matching only on the exact row is what let
    statement lines duplicate expenses that were already recorded.
    """
    kinds = ('CREDIT_CARD', 'OTHER')
    q = Q(pk=card.pk)
    if card.last4:
        q |= Q(kind__in=kinds, last4=card.last4)
    if card.institution:
        stem = re.sub(r'\s+(Bank|Card)\b', '', card.institution, flags=re.I).strip()
        inst_q = Q(institution__iexact=card.institution)
        if stem and len(stem) >= 3:
            inst_q |= Q(institution__icontains=stem)
        q |= Q(kind__in=kinds, last4='') & inst_q
        if not card.last4:
            q |= Q(kind='CREDIT_CARD') & inst_q
    return set(PaymentSource.objects.filter(group_id=card.group_id).filter(q).values_list('pk', flat=True))


def _apply_summary(statement, summary):
    for field in ('statement_date', 'due_date', 'total_due', 'min_due', 'period_start', 'period_end'):
        value = getattr(summary, field)
        if value is not None and getattr(statement, field) is None:
            setattr(statement, field, value)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _ai_lines(text):
    out = []
    for row in ai.extract_statement_lines(text):
        d = parse_date(row.date)
        amount = to_decimal(str(row.amount))
        if d and amount:
            out.append(ParsedLine(txn_date=d, description=(row.description or '')[:255], amount=abs(amount),
                                  is_credit=bool(row.is_credit) or amount < 0))
    return out


def _lines_from_text(text):
    """Regex first; AI when regex finds nothing or clearly misses rows (multi-line layouts)."""
    lines = parse_statement_lines(text)
    date_rows = sum(1 for row in text.splitlines() if _DATE_LED_ROW.match(row))
    if lines and len(lines) >= REGEX_COVERAGE * date_rows:
        return lines
    ai_lines = _ai_lines(text)
    return ai_lines if len(ai_lines) > len(lines) else lines


# ---------------------------------------------------------------------------
# Statement-level de-duplication
# ---------------------------------------------------------------------------

def find_duplicate(statement, lines=None):
    """An already-parsed statement that is the same document / billing cycle as this one."""
    if statement.pdf_sha256:
        hit = CardStatement.objects.filter(
            group_id=statement.group_id, pdf_sha256=statement.pdf_sha256
        ).exclude(status='DUPLICATE').exclude(pk=statement.pk).first()
        if hit:
            return hit
    others = CardStatement.objects.filter(group_id=statement.group_id, status='PARSED').exclude(pk=statement.pk)
    family = others.filter(payment_source_id__in=card_family_ids(statement.payment_source))
    end = statement.period_end or statement.statement_date
    if end:
        hit = family.filter(Q(period_end=end) | Q(statement_date=end)).first()
        if hit:
            return hit
    if lines:
        keys = Counter((ln.txn_date, ln.amount, ln.is_credit) for ln in lines)
        lo, hi = min(ln.txn_date for ln in lines), max(ln.txn_date for ln in lines)
        for other in family.filter(lines__txn_date__range=(lo, hi)).distinct()[:12]:
            theirs = Counter(other.lines.values_list('txn_date', 'amount', 'is_credit'))
            if sum((keys & theirs).values()) >= DUPLICATE_LINE_SHARE * sum(keys.values()):
                return other
    return None


def _mark_duplicate(statement, original):
    for field in ('due_date', 'total_due', 'min_due', 'period_start', 'period_end', 'statement_date'):
        if getattr(original, field) is None and getattr(statement, field) is not None:
            setattr(original, field, getattr(statement, field))
    original.save()
    statement.status = 'DUPLICATE'
    statement.duplicate_of = original
    statement.pdf_blob = None
    statement.save()


def _absorb_shells(statement):
    """Retire totals-only / unreadable copies of this cycle so it is reminded and counted once."""
    end = statement.period_end or statement.statement_date
    if not end and statement.lines.exists():
        dates = list(statement.lines.values_list('txn_date', flat=True))
        if dates:
            statement.period_start = min(dates)
            statement.period_end = max(dates)
            statement.statement_date = statement.period_end
            statement.save(update_fields=['statement_date', 'period_start', 'period_end'])
            end = statement.period_end
    if not end:
        return
    shells = (CardStatement.objects
              .filter(group_id=statement.group_id, status__in=('BODY_ONLY', 'FAILED'),
                      payment_source_id__in=card_family_ids(statement.payment_source))
              .filter(
                  Q(statement_date=end) | Q(period_end=end) |
                  Q(due_date=statement.due_date, due_date__isnull=False) |
                  Q(due_date__gte=end, due_date__lte=end + datetime.timedelta(days=35))
              )
              .exclude(pk=statement.pk))
    for shell in shells:
        if shell.is_paid and not statement.is_paid:
            statement.is_paid, statement.paid_at, statement.paid_amount = True, shell.paid_at, shell.paid_amount
            statement.save(update_fields=['is_paid', 'paid_at', 'paid_amount'])
        _mark_duplicate(shell, statement)


def read_pdf(statement, data, password=''):
    """Parse a statement PDF into lines + totals. Keeps the PDF if a password is needed."""
    if data:
        statement.pdf_sha256 = hashlib.sha256(data).hexdigest()
        duplicate = find_duplicate(statement)
        if duplicate:
            _mark_duplicate(statement, duplicate)
            return statement

    passwords = []
    if password:
        passwords.append(password)
    if statement.payment_source.statement_password:
        passwords.append(statement.payment_source.statement_password)
    for fid in card_family_ids(statement.payment_source):
        if fid == statement.payment_source_id:
            continue
        fc = PaymentSource.objects.filter(pk=fid).first()
        if fc and fc.statement_password and fc.statement_password not in passwords:
            passwords.append(fc.statement_password)

    text = None
    if passwords:
        for pw in passwords:
            try:
                text = pdf_text(data, pw)
                break
            except PdfPasswordRequired:
                continue
            except Exception:
                break

    if text is None:
        try:
            text = pdf_text(data, '')
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

    summary = parse_statement_summary('', '', text)
    _apply_summary(statement, summary)
    if summary.last4 and not statement.payment_source.last4:
        existing_card = find_card(
            statement.group, statement.payment_source.institution or summary.institution, summary.last4
        )
        if existing_card and existing_card.pk != statement.payment_source.pk:
            statement.payment_source = existing_card
            statement.save(update_fields=['payment_source'])
        else:
            statement.payment_source.last4 = summary.last4
            if summary.institution and not statement.payment_source.institution:
                statement.payment_source.institution = summary.institution
                statement.payment_source.save(update_fields=['last4', 'institution'])
            else:
                statement.payment_source.save(update_fields=['last4'])

    duplicate = find_duplicate(statement)
    lines = [] if duplicate else _lines_from_text(text)
    if not duplicate and lines:
        duplicate = find_duplicate(statement, lines)
    if duplicate:
        _mark_duplicate(statement, duplicate)
        return statement

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
        _absorb_shells(statement)
        reconcile(statement)
    return statement


def retry_locked_statements(group, card=None):
    """Re-open password-locked PDFs once a password has been saved for their card or family."""
    qs = (CardStatement.objects.filter(group=group, status='NEEDS_PASSWORD', pdf_blob__isnull=False)
          .select_related('payment_source'))
    if card is not None:
        qs = qs.filter(payment_source=card)
    opened = 0
    for st in qs:
        read_pdf(st, crypto.decrypt_bytes(st.pdf_blob))
        opened += st.status != 'NEEDS_PASSWORD'
    return opened


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def _period(statement):
    lines = list(statement.lines.all())
    if statement.period_start and statement.period_end:
        return statement.period_start, statement.period_end
    if lines:
        return min(ln.txn_date for ln in lines), max(ln.txn_date for ln in lines)
    end = statement.statement_date or statement.created_at.date()
    return end - datetime.timedelta(days=31), end


def _similarity(line_key, expense):
    key = expense.merchant_key or ''
    if not line_key or not key:
        return 0.0
    if len(key) >= 4 and (key in line_key or line_key in key):
        return 0.9
    return difflib.SequenceMatcher(None, line_key, key).ratio()


def _line_key(line):
    return normalize_merchant(line.description)[1]


def _rule_match(line, candidates, family):
    """Best amount+date candidate, or None when it is not clearly the one."""
    key = _line_key(line)
    scored = []
    for e in candidates:
        if abs(e.amount - line.amount) > AMOUNT_TOLERANCE:
            continue
        gap = abs((e.txn_date - line.txn_date).days)
        if gap > DATE_TOLERANCE_DAYS:
            continue
        sim = _similarity(key, e)
        score = sim + (1 - gap / (DATE_TOLERANCE_DAYS + 1)) + (1 if e.amount == line.amount else 0)
        scored.append((score, sim, e))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda s: s[0], reverse=True)
    best_score, best_sim, best = scored[0]
    confidence = round(min(1.0, best_score / 3), 2)
    if len(scored) == 1:
        # Same card + same amount + same few days is decisive; a card-less entry also needs a name hint.
        if best.payment_source_id in family or best_sim >= SINGLE_CANDIDATE_SIMILARITY:
            return best, confidence
        return None, 0.0
    if best_sim >= RULE_SIMILARITY and best_score - scored[1][0] >= RULE_MARGIN:
        return best, confidence
    return None, 0.0


def _loose_candidates(line, candidates):
    """Plausible duplicates the rules could not settle: near amount or foreign currency, nearby date."""
    key = _line_key(line)
    window = max(AMOUNT_TOLERANCE, line.amount * LOOSE_AMOUNT_RATIO)
    ranked = []
    for e in candidates:
        gap = abs((e.txn_date - line.txn_date).days)
        if gap > LOOSE_DATE_DAYS:
            continue
        close = abs(e.amount - line.amount) <= window
        if not close and e.currency == 'INR':
            continue
        ranked.append((not close, -_similarity(key, e), gap, e))
    ranked.sort(key=lambda r: r[:3])
    return [r[3] for r in ranked[:MAX_AI_CANDIDATES]]


def _ai_item(line, candidates):
    return {
        'line_id': line.pk,
        'date': line.txn_date.isoformat(),
        'description': line.description,
        'amount': str(line.amount),
        'direction': 'CREDIT' if line.is_credit else 'DEBIT',
        'candidates': [
            {
                'expense_id': e.pk, 'date': e.txn_date.isoformat(), 'merchant': e.merchant,
                'raw': (e.merchant_raw or '')[:80], 'amount': str(e.amount), 'currency': e.currency,
                'channel': e.channel, 'recorded_from': e.source,
            }
            for e in candidates
        ],
    }


def _link(line, expense, method, confidence=None, reason=''):
    line.matched_expense = expense
    # Re-reading a statement re-finds the rows it added earlier; they still count as "added".
    line.was_added = expense.source == 'STATEMENT' and expense.statement_id == line.statement_id
    line.match_method = method
    line.match_confidence = confidence
    line.needs_review = False
    line.suggested_expense = None
    line.match_reason = (reason or '')[:255]
    line.save(update_fields=_LINE_FIELDS)
    if not expense.payment_source_id:
        expense.payment_source = line.statement.payment_source
        expense.save(update_fields=['payment_source'])


def _add_line(statement, line, cats, method='', confidence=None, reason=''):
    from .anomaly import apply_flags
    from .services import build_expense

    card = statement.payment_source
    direction = 'CREDIT' if line.is_credit else 'DEBIT'
    emi = parse_emi_details(line.description)
    display, key = normalize_merchant(line.description)
    merchant = emi['merchant'] if (emi['is_emi'] and emi['merchant']) else (display or line.description)
    parsed = ParsedTransaction(
        amount=line.amount, direction=direction, txn_date=line.txn_date, merchant=merchant,
        merchant_raw=line.description, merchant_key=key, instrument='CREDIT_CARD', channel='CARD',
        institution=card.institution, last4=card.last4,
        is_emi=emi['is_emi'], emi_reference=emi['reference'], emi_installment_num=emi['installment_num'],
        emi_total_installments=emi['total_installments'], emi_component=emi['component'],
    )
    expense, created = build_expense(
        statement.group, parsed, source='STATEMENT', member=card.owner, statement=statement,
        dedupe_key=f'st:{statement.pk}:{line.pk}', cats=cats,
    )
    if created:
        expense.payment_source = card
        expense.notes = 'Found on card statement — no email alert was received'
        expense.save(update_fields=['payment_source', 'notes'])
        apply_flags(expense)
    line.matched_expense = expense
    line.was_added = True
    line.match_method = method
    line.match_confidence = confidence
    line.needs_review = False
    line.suggested_expense = None
    line.match_reason = (reason or '')[:255]
    line.save(update_fields=_LINE_FIELDS)
    return int(created)


def _park(line, suggestion, verdict):
    line.matched_expense = None
    line.was_added = False
    line.match_method = ''
    line.needs_review = True
    line.suggested_expense = suggestion
    line.match_confidence = verdict.confidence if verdict else None
    line.match_reason = ((verdict.reason if verdict and verdict.reason else '')
                         or 'Looks like an expense already recorded — confirm before adding')[:255]
    line.save(update_fields=_LINE_FIELDS)


def _refresh_counts(statement):
    lines = statement.lines
    statement.line_count = lines.count()
    statement.added_count = lines.filter(was_added=True).count()
    statement.matched_count = lines.filter(matched_expense__isnull=False, was_added=False).count()
    statement.review_count = lines.filter(needs_review=True).count()
    statement.save(update_fields=['line_count', 'added_count', 'matched_count', 'review_count'])


@transaction.atomic
def reconcile(statement):
    """Match statement lines to recorded expenses and add only what is genuinely missing.

    Idempotent: lines already linked are left alone; unmatched and review lines are re-evaluated.
    Returns (matched_count, added_this_run).
    """
    from .services import categories_by_name

    card = statement.payment_source
    family = card_family_ids(card)
    start, end = _period(statement)
    lines = list(statement.lines.all())
    claimed = set(StatementLine.objects.filter(statement__group=statement.group, matched_expense__isnull=False)
                  .exclude(statement=statement).exclude(statement__status='DUPLICATE').values_list('matched_expense_id', flat=True))
    used = claimed | {ln.matched_expense_id for ln in lines if ln.matched_expense_id}
    window = datetime.timedelta(days=LOOSE_DATE_DAYS)
    pool = [
        e for e in Expense.objects.filter(
            group=statement.group, is_deleted=False,
            txn_date__gte=start - window, txn_date__lte=end + window,
        ).filter(Q(payment_source_id__in=family) | Q(payment_source__isnull=True))
        if e.pk not in claimed
    ]
    cats = categories_by_name(statement.group)
    added = 0

    def free(direction):
        return [e for e in pool if e.direction == direction and e.pk not in used]

    # Pass 1 — deterministic matches for every line first, so ordering can't steal a match.
    todo = []
    for line in lines:
        if line.matched_expense_id:
            continue
        if line.is_credit and _is_payment(line.description):
            if line.match_method != 'SKIP' or line.needs_review:
                line.match_method, line.needs_review, line.suggested_expense = 'SKIP', False, None
                line.save(update_fields=_LINE_FIELDS)
            continue

        if line.is_credit:
            # Check if this refund credit matches an existing CREDIT expense (e.g. from refund email)
            c_match, c_conf = _rule_match(line, free('CREDIT'), family)
            if c_match:
                used.add(c_match.pk)
                _link(line, c_match, 'RULE', c_conf)
                if not c_match.refund_of_id:
                    d_cand = _find_refund_debit(line, free('DEBIT'), family)
                    if d_cand:
                        c_match.refund_of = d_cand
                        c_match.save(update_fields=['refund_of'])
                        d_cand.refunded_amount = min(
                            d_cand.amount,
                            (d_cand.refunded_amount or Decimal('0.00')) + line.amount,
                        )
                        d_cand.refund_date = line.txn_date
                        d_cand.save(update_fields=['refunded_amount', 'refund_date'])
                continue

            # Directly look for the matching purchase (DEBIT)
            d_match = _find_refund_debit(line, free('DEBIT'), family)
            if d_match:
                d_match.refunded_amount = (d_match.refunded_amount or Decimal('0.00')) + line.amount
                d_match.refund_date = line.txn_date
                d_match.save(update_fields=['refunded_amount', 'refund_date'])
                line.matched_expense = d_match
                line.was_added = False
                line.match_method = 'RULE'
                line.match_confidence = 0.95
                line.match_reason = f'Refund for {d_match.merchant} on {d_match.txn_date}'[:255]
                line.needs_review = False
                line.suggested_expense = None
                line.save(update_fields=_LINE_FIELDS)
                continue

        direction = 'CREDIT' if line.is_credit else 'DEBIT'
        match, confidence = _rule_match(line, free(direction), family)
        if match:
            used.add(match.pk)
            _link(line, match, 'RULE', confidence)
        else:
            todo.append(line)

    # Pass 2 — leftovers: add the clearly new, ask AI about plausible duplicates.
    pending = []
    for line in todo:
        candidates = _loose_candidates(line, free('CREDIT' if line.is_credit else 'DEBIT'))
        if candidates:
            pending.append((line, candidates))
        else:
            added += _add_line(statement, line, cats)

    verdicts = ai.match_statement_lines([_ai_item(ln, cands) for ln, cands in pending]) if pending else {}
    for line, candidates in pending:
        verdict = verdicts.get(line.pk)
        available = [e for e in candidates if e.pk not in used]
        if verdict and verdict.expense_id and verdict.confidence >= AI_MATCH_CONFIDENCE:
            match = next((e for e in available if e.pk == verdict.expense_id), None)
            if match:
                used.add(match.pk)
                _link(line, match, 'AI', verdict.confidence, verdict.reason)
                continue
        if verdict and verdict.expense_id is None and verdict.confidence >= AI_NEW_CONFIDENCE:
            added += _add_line(statement, line, cats, 'AI', verdict.confidence, verdict.reason)
            continue
        if not available:
            added += _add_line(statement, line, cats)
            continue
        suggestion = next((e for e in available if verdict and e.pk == verdict.expense_id), available[0])
        _park(line, suggestion, verdict)

    _refresh_counts(statement)
    return statement.matched_count, added


def _find_refund_debit(line, debits, family):
    """Find the original DEBIT purchase that corresponds to this credit/refund line."""
    line_key = _line_key(line)
    norm_disp, norm_key = normalize_merchant(line.description)
    clean_desc = (line.description or '').lower()

    # Pass 1: exact amount and matching merchant
    for d in debits:
        if d.amount != line.amount:
            continue
        sim = _similarity(line_key, d)
        d_m = (d.merchant or '').lower()
        if (
            sim >= 0.6
            or (norm_key and norm_key in (d.merchant_key or ''))
            or (d.merchant_key and d.merchant_key in norm_key)
            or (d_m and d_m in clean_desc)
            or (norm_disp and norm_disp.lower() in d_m)
        ):
            return d

    # Pass 2: partial refund (debit amount >= line amount) with strong merchant match within 60 days
    for d in debits:
        if d.amount < line.amount:
            continue
        sim = _similarity(line_key, d)
        d_m = (d.merchant or '').lower()
        if (
            (sim >= 0.85 or (norm_key and norm_key == d.merchant_key) or (d_m and d_m in clean_desc))
            and abs((line.txn_date - d.txn_date).days) <= 60
        ):
            return d

    return None


def reconcile_refunds(group):
    """Pair unmatched CREDIT expenses (refunds/returns) with their original DEBIT purchases."""
    credits = Expense.objects.filter(
        group=group,
        is_deleted=False,
        direction='CREDIT',
        refund_of__isnull=True,
    ).exclude(category__name='Investments')

    linked = 0
    for c in credits:
        if _is_payment(c.merchant_raw or c.merchant or c.email_subject):
            continue
        candidates = Expense.objects.filter(
            group=group,
            is_deleted=False,
            direction='DEBIT',
            txn_date__gte=c.txn_date - datetime.timedelta(days=90),
            txn_date__lte=c.txn_date + datetime.timedelta(days=30),
        )
        if c.payment_source_id:
            family = card_family_ids(c.payment_source)
            candidates = candidates.filter(Q(payment_source_id__in=family) | Q(payment_source__isnull=True))

        c_key = c.merchant_key or normalize_merchant(c.merchant or c.merchant_raw)[1]
        c_m = (c.merchant or '').lower()
        best_debit = None
        for d in candidates:
            rem = d.amount - (d.refunded_amount or Decimal('0.00'))
            if rem < c.amount:
                continue
            d_key = d.merchant_key or normalize_merchant(d.merchant or d.merchant_raw)[1]
            sim = 1.0 if (c_key and d_key and (c_key == d_key or c_key in d_key or d_key in c_key)) else 0.0
            d_m = (d.merchant or '').lower()
            if sim < 0.6 and c_m and d_m and (c_m in d_m or d_m in c_m):
                sim = 0.8
            if sim >= 0.6:
                if rem == c.amount:
                    best_debit = d
                    break
                elif rem >= c.amount and not best_debit:
                    best_debit = d

        if best_debit:
            c.refund_of = best_debit
            c.save(update_fields=['refund_of'])
            best_debit.refunded_amount = min(
                best_debit.amount,
                (best_debit.refunded_amount or Decimal('0.00')) + c.amount,
            )
            best_debit.refund_date = c.txn_date
            best_debit.save(update_fields=['refunded_amount', 'refund_date'])
            linked += 1

    return linked


@transaction.atomic
def resolve_line(line, action):
    """Human decision on a parked line: 'link' to the suggested expense, or 'add' it as new."""
    from .services import categories_by_name

    statement = line.statement
    if action == 'link':
        target = line.suggested_expense
        if (not target or target.is_deleted
                or StatementLine.objects.filter(matched_expense=target).exclude(pk=line.pk).exists()):
            return False
        _link(line, target, 'USER', 1.0, 'Confirmed as the same transaction')
    elif action == 'add':
        _add_line(statement, line, categories_by_name(statement.group), 'USER', 1.0,
                  'Confirmed as a separate transaction')
    else:
        return False
    _refresh_counts(statement)
    return True


_PAYMENT_DESC = re.compile(
    r'\b(payment\s+received|thank\s+you(?:\s+for\s+the\s+payment)?|bbps\s+payment|'
    r'autopay|auto\s+debit|autodebit|neft\s+payment|imps\s+payment|upi\s+payment|'
    r'net\s?banking\s+payment|cheque\s+payment|chq\s+payment|billdesk|cred\s+payment|'
    r'bppy\s+(?:cc\s+)?payment|bppy|billpay|upicc-\d{2}-\d{2}-\d{4}|cc\s+payment|'
    r'credit\s+card\s+payment|cred\s+club|standing\s+instruction)\b|'
    r'payment\s*-\s*|'
    r'payment\s+ref|'
    r'cr\s*-\s*payment',
    re.I,
)


def _is_payment(description):
    d = description.lower()
    if 'refund' in d or 'reversal' in d or 'chargeback' in d or 'cashback' in d or 'reward' in d or 'credit adj' in d:
        return False
    return bool(_PAYMENT_DESC.search(d))


def ingest_statement_email(group, account, message_id, sender, subject, body, pdfs, fetch_pdf):
    """Create a CardStatement from a statement email. fetch_pdf(descriptor) -> bytes."""
    summary = parse_statement_summary(sender, subject, body)
    card = get_or_create_card(group, summary.institution, summary.last4, owner=account.user)
    statement, created = CardStatement.objects.get_or_create(
        group=group, gmail_message_id=message_id,
        defaults={'payment_source': card, 'gmail_account': account},
    )
    if not created and statement.status in ('PARSED', 'DUPLICATE'):
        return statement
    _apply_summary(statement, summary)
    statement.save()
    for pdf in pdfs[:MAX_PDFS_PER_EMAIL]:
        try:
            data = fetch_pdf(pdf)
        except Exception:
            logger.exception('Could not download statement PDF for %s', message_id)
            continue
        if data and len(data) <= MAX_PDF_BYTES:
            read_pdf(statement, data)
            if statement.status in ('PARSED', 'DUPLICATE', 'NEEDS_PASSWORD'):
                break
    if statement.status == 'BODY_ONLY':
        duplicate = find_duplicate(statement)
        if duplicate:
            _mark_duplicate(statement, duplicate)
    return statement


def record_card_payment(group, amount, last4, institution, paid_on):
    """Mark the latest unpaid statement of the card as paid when a payment-received email arrives."""
    card = find_card(group, institution, last4)
    if not card or not amount:
        return None
    statement = (CardStatement.objects.filter(group=group, payment_source_id__in=card_family_ids(card), is_paid=False)
                 .exclude(status='DUPLICATE')
                 .order_by('-statement_date', '-created_at').first())
    if not statement:
        return None
    current_paid = (statement.paid_amount or Decimal('0')) + amount
    statement.paid_amount = current_paid
    target = statement.total_due or statement.min_due or Decimal('0')
    if not target or current_paid >= target - AMOUNT_TOLERANCE:
        statement.is_paid = True
        statement.paid_at = paid_on
        statement.save(update_fields=['is_paid', 'paid_at', 'paid_amount'])
    else:
        statement.save(update_fields=['paid_amount'])
    return statement


def due_reminders(group, today=None):
    """Unpaid statements due within the reminder window that haven't been reminded today."""
    today = today or datetime.date.today()
    out = []
    for st in (CardStatement.objects.filter(group=group, is_paid=False, due_date__isnull=False,
                                            due_date__gte=today - datetime.timedelta(days=3))
               .exclude(status='DUPLICATE')
               .select_related('payment_source')):
        days_left = (st.due_date - today).days
        if days_left in REMINDER_DAYS or days_left < 0:
            if st.reminder_sent_on != today:
                out.append((st, days_left))
    return out


def auto_track_statement_payments(group, since_days=60):
    """Automatically track and reconcile credit card bill payments against statements.

    Handles:
    - Full payments: automatically marks statement as paid (is_paid=True).
    - Multi-part / partial payments: tracks paid_amount and remaining due.
    """
    cutoff = datetime.date.today() - datetime.timedelta(days=since_days)
    statements = list(
        CardStatement.objects.filter(
            group=group,
            total_due__isnull=False,
            total_due__gt=0,
        )
        .filter(Q(is_paid=False) | Q(created_at__date__gte=cutoff))
        .exclude(status='DUPLICATE')
        .select_related('payment_source')
    )
    if not statements:
        return

    today_date = datetime.date.today()
    for st in statements:
        card = st.payment_source
        if not card:
            continue
        family_ids = card_family_ids(card)
        if card.last4:
            family_ids |= set(PaymentSource.objects.filter(group=group, last4=card.last4).values_list('pk', flat=True))

        start_date = (st.statement_date - datetime.timedelta(days=5)) if st.statement_date else (
            st.due_date - datetime.timedelta(days=45) if st.due_date else (today_date - datetime.timedelta(days=60))
        )
        end_date = max(today_date, (st.due_date + datetime.timedelta(days=45)) if st.due_date else today_date)

        # Look for credit transactions on this credit card (payment receipts)
        card_credits = list(
            Expense.objects.filter(
                group=group,
                payment_source_id__in=family_ids,
                direction='CREDIT',
                txn_date__gte=start_date,
                txn_date__lte=end_date,
                is_deleted=False,
            ).exclude(refund_of__isnull=False)
        )

        for c in card_credits:
            updates_c = []
            if not c.merchant or c.merchant in ('Unknown merchant', 'Unknown'):
                c.merchant = 'Credit Card Bill Payment'
                updates_c.append('merchant')
            if c.category and c.category.name == 'Transfers':
                from .categories import categories_by_name
                cats = categories_by_name(group)
                if 'Credit Card Payment' in cats:
                    c.category = cats['Credit Card Payment']
                    updates_c.append('category')
            if updates_c:
                c.save(update_fields=updates_c)

            # Heal twin debit if filed under Transfers or uncategorised
            twin_debit = (
                Expense.objects.filter(
                    group=group,
                    direction='DEBIT',
                    amount=c.amount,
                    txn_date__gte=c.txn_date - datetime.timedelta(days=4),
                    txn_date__lte=c.txn_date + datetime.timedelta(days=4),
                    is_deleted=False,
                )
                .filter(Q(category__name='Transfers') | Q(category__isnull=True))
                .first()
            )
            if twin_debit:
                from .categories import categories_by_name
                cats = categories_by_name(group)
                if 'Credit Card Payment' in cats:
                    twin_debit.category = cats['Credit Card Payment']
                    twin_debit.save(update_fields=['category'])

        total_paid = sum((c.amount for c in card_credits), Decimal('0.00'))

        # Also check for debits explicitly referencing this card's last4 under Credit Card Payment
        if card.last4:
            debit_payments = list(
                Expense.objects.filter(
                    group=group,
                    direction='DEBIT',
                    category__name__in=('Credit Card Payment', 'Transfers'),
                    merchant_raw__icontains=card.last4,
                    txn_date__gte=start_date,
                    txn_date__lte=end_date,
                    is_deleted=False,
                )
            )
            for d in debit_payments:
                if not any(abs(c.amount - d.amount) <= Decimal('1.00') for c in card_credits):
                    total_paid += d.amount

        if total_paid > Decimal('0.00'):
            target_paid = total_paid >= (st.total_due - Decimal('1.00'))
            latest_date = max((c.txn_date for c in card_credits), default=None)
            updates = []
            if st.paid_amount != total_paid:
                st.paid_amount = total_paid
                updates.append('paid_amount')
            if target_paid and not st.is_paid:
                st.is_paid = True
                st.paid_at = latest_date or st.paid_at or today_date
                updates.extend(['is_paid', 'paid_at'])
            elif not target_paid and st.is_paid:
                st.is_paid = False
                st.paid_at = None
                updates.extend(['is_paid', 'paid_at'])
            if updates:
                st.save(update_fields=updates)


def upcoming_dues(group, today=None, horizon_days=21):
    today = today or datetime.date.today()
    auto_track_statement_payments(group)
    dues = list(
        CardStatement.objects.filter(
            group=group, is_paid=False, due_date__isnull=False,
            due_date__gte=today - datetime.timedelta(days=30),
            due_date__lte=today + datetime.timedelta(days=horizon_days),
        ).exclude(status='DUPLICATE').select_related('payment_source').order_by('due_date')
    )
    for st in dues:
        tot = st.total_due or st.min_due or Decimal('0.00')
        paid = st.paid_amount or Decimal('0.00')
        st.remaining_due = max(Decimal('0.00'), tot - paid)
        st.is_partial = paid > Decimal('0.00') and st.remaining_due > Decimal('0.00')
    return dues
