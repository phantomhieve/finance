"""Parse Indian bank and card alert emails into structured transactions and statement summaries.

Deterministic regex engine first (fast, private, zero-cost); callers may fall back to the AI extractor
in ``expenses.ai`` when an email looks transactional but deterministic patterns cannot parse it.
"""
from __future__ import annotations

import datetime
import html
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# ---------------------------------------------------------------------------
# Text helpers & HTML Cleaning
# ---------------------------------------------------------------------------

_TAG_DROP = re.compile(r'<(script|style|head)\b.*?</\1\s*>|<!--.*?-->', re.I | re.S)
_TAG_BREAKS = re.compile(r'<\s*(br|/p|/div|/tr|/li|/h\d)\b[^>]*>', re.I)
_TAG_CELLS = re.compile(r'<\s*/t[dh]\s*>', re.I)
_TAG_ANY = re.compile(r'<[^>]+>')


def html_to_text(markup: str | None) -> str:
    """Convert raw HTML email content into clean plaintext preserving linebreaks and table cells."""
    if not markup:
        return ''
    text = _TAG_DROP.sub(' ', markup)
    text = _TAG_BREAKS.sub('\n', text)
    text = _TAG_CELLS.sub(' ', text)
    text = _TAG_ANY.sub(' ', text)
    text = html.unescape(text).replace('\xa0', ' ').replace('\u200b', '')
    return clean_text(text)


def clean_text(text: str | None) -> str:
    """Normalize multi-spaces within lines and strip empty line runs."""
    lines = [re.sub(r'[ \t\r\f\v]+', ' ', ln).strip() for ln in (text or '').splitlines()]
    return '\n'.join(ln for ln in lines if ln)


def mask_sensitive(text: str | None) -> str:
    """Mask long digit runs (account / card / reference numbers) before sending text to an LLM."""
    if not text:
        return ''
    # Mask card numbers formatted with dashes or spaces: 1234-5678-9012-3456
    masked = re.sub(
        r'\b\d{4}[-\s]\d{4}[-\s]\d{4}[-\s](\d{4})\b',
        lambda m: 'XXXX-XXXX-XXXX-' + m.group(1),
        text,
    )
    # Mask contiguous digit runs >= 6 digits, preserving last 4
    return re.sub(
        r'\d{6,}',
        lambda m: 'X' * (len(m.group()) - 4) + m.group()[-4:],
        masked,
    )


def to_decimal(raw: object) -> Decimal | None:
    """Safely convert currency string or number to Decimal without float imprecision."""
    if raw is None:
        return None
    try:
        clean = re.sub(r'[^\d.-]', '', str(raw).strip())
        return Decimal(clean) if clean else None
    except (InvalidOperation, ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Institutions
# ---------------------------------------------------------------------------

# (substring of sender address or body, display name). Order matters: more specific first.
_INSTITUTIONS: list[tuple[str, str]] = [
    ('sbicard', 'SBI Card'),
    ('onlinesbi', 'SBI'),
    ('sbi.co.in', 'SBI'),
    ('hdfcbank', 'HDFC Bank'),
    ('hdfc bank', 'HDFC Bank'),
    ('icicibank', 'ICICI Bank'),
    ('icici bank', 'ICICI Bank'),
    ('axisbank', 'Axis Bank'),
    ('axis.bank', 'Axis Bank'),
    ('axis bank', 'Axis Bank'),
    ('kotak', 'Kotak Bank'),
    ('americanexpress', 'American Express'),
    ('american express', 'American Express'),
    ('aexp', 'American Express'),
    ('amex', 'American Express'),
    ('yesbank', 'Yes Bank'),
    ('yes bank', 'Yes Bank'),
    ('indusind', 'IndusInd Bank'),
    ('idfcfirst', 'IDFC First Bank'),
    ('idfc first', 'IDFC First Bank'),
    ('aubank', 'AU Bank'),
    ('federalbank', 'Federal Bank'),
    ('rblbank', 'RBL Bank'),
    ('hsbc', 'HSBC'),
    ('sc.com', 'Standard Chartered'),
    ('standard chartered', 'Standard Chartered'),
    ('bobcard', 'BOB Card'),
    ('bankofbaroda', 'Bank of Baroda'),
    ('pnb', 'PNB'),
    ('canarabank', 'Canara Bank'),
    ('unionbank', 'Union Bank'),
    ('onecard', 'OneCard'),
    ('slice', 'Slice'),
    ('paytm', 'Paytm'),
    ('amazonpay', 'Amazon Pay'),
    ('jupiter', 'Jupiter'),
    ('fi.money', 'Fi'),
    ('cred.club', 'CRED'),
    ('cred', 'CRED'),
    ('tataneu', 'Tata Neu'),
    ('postpe', 'PostPe'),
    ('navi', 'Navi'),
    ('airtel payments bank', 'Airtel Payments Bank'),
    ('airtel bank', 'Airtel Payments Bank'),
]


def detect_institution(sender: str | None, body: str | None) -> str:
    """Identify the bank, credit card issuer, or payment app from sender or body text."""
    sender_l = (sender or '').lower()
    for needle, name in _INSTITUTIONS:
        if needle in sender_l:
            return name
    body_l = (body or '').lower()[:700]
    for needle, name in _INSTITUTIONS:
        if ' ' in needle and needle in body_l:
            return name
    for needle, name in _INSTITUTIONS:
        if needle in body_l[:300]:
            return name
    return ''


# ---------------------------------------------------------------------------
# Classification & Amount Extraction
# ---------------------------------------------------------------------------

# Standard Indian currency prefix followed by amount
_AMOUNT_CORE = r'(?:INR\.?|Rs\.?|₹|INR\s*[:\-]|Rs\s*[:\-])\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)'
_AMOUNT_RE = re.compile(_AMOUNT_CORE, re.I)

# Transaction-linked amount search: binds directly to debit/credit verbs to avoid available balance
_TXN_AMOUNT_RE = re.compile(
    r'(?:debited\s*(?:by|with|for)?|spent|charged|withdrawn|deducted|paid|credited\s*(?:with|by)?|received|refunded|payment\s+of|txn\s+of|transaction\s+of|amount\s*[:\-])'
    r'\s*(?:INR\.?|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
    re.I,
)

# Currency suffix fallback (e.g. "1,500.00 INR" or "1500/-")
_AMOUNT_SUFFIX_RE = re.compile(
    r'\b([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:INR|Rs\.?|/-)\b',
    re.I,
)

_FOREIGN_AMOUNT_RE = re.compile(
    r'\b(USD|EUR|GBP|AED|SGD|AUD|CAD|JPY|CHF|THB)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
    re.I,
)

_DEBIT_WORDS = re.compile(
    r'\b(debited|spent|used\s+for|been\s+used|for\s+using|withdrawn|deducted|charged|paid|payment\s+made|sent\s+to|transfer(?:red)?\s+to|purchase|transaction\s+of|txn\s+of)\b',
    re.I,
)

# High-confidence explicit debit phrases
_DEBIT_EXPLICIT_RE = re.compile(
    r'\b(debited\s+(?:from|with|for)|debited\s+to\s+your\s+account|spent\s+(?:at|on|for)|charged\s+to|paid\s+to|transferred\s+to|withdrawn\s+from)\b',
    re.I,
)

# Explicit credit phrases — notice loose "received" is restricted so order alerts don't flip to credit
_CREDIT_WORDS = re.compile(
    r'\b(credited|refund(?:ed)?|reversal|reversed|deposited|cashback|(?:amount|money|funds?)\s+(?:has\s+been\s+)?received|received\s+(?:INR|Rs\.?|₹)\s*[0-9]|received\s+from|salary\s+credited)\b',
    re.I,
)

# High-confidence explicit credit phrases
_CREDIT_EXPLICIT_RE = re.compile(
    r'\b(credited\s+to|refund\s+of|refunded\s+to|cashback\s+credited|deposited\s+in(?:to)?|received\s+from|(?:amount|money)\s+received\s+from)\b',
    re.I,
)

# Merchant purchase receipts (e.g. Swiggy order, Google Cloud invoice, Airtel bill payment receipt) -> DEBIT
_PAYMENT_RECEIPT_WORDS = re.compile(
    r'\b(?:we(?:\'?ve|\s+have)?\s+received\s+(?:your\s+)?payment'
    r'|payment\s+received'
    r'|payment\s+receipt'
    r'|receipt\s+for\s+(?:your\s+)?payment'
    r'|thank\s+you\s+for\s+(?:your\s+)?payment'
    r'|payment\s+was\s+successful'
    r'|payment\s+successful'
    r'|payment\s+confirmed)\b',
    re.I,
)

_NOISE = re.compile(
    r'\b(otp|one[\s-]?time\s+password|verification\s+code|do\s+not\s+share\s+(?:this|the)\s+(?:otp|code)'
    r'|pre-?approved|limited\s+period|apply\s+now|avail\s+now|exclusive\s+offer|win\s+(?:up\s+to|a)'
    r'|will\s+be\s+debited|is\s+due\s+on|due\s+for\s+renewal|has\s+been\s+declined|was\s+declined'
    r'|transaction\s+(?:has\s+)?failed|could\s+not\s+be\s+processed|insufficient\s+(?:funds|balance)'
    r'|mandate\s+(?:has\s+been\s+)?(?:registered|created)|standing\s+instruction\s+registered'
    r'|autopay\s+(?:scheduled|registered|created)|payment\s+failed|unsuccessful)\b',
    re.I,
)

_STATEMENT_SUBJECT = re.compile(r'\b(e-?statement|statement)\b', re.I)
_STATEMENT_BODY = re.compile(r'(total\s+(?:amount\s+)?due|minimum\s+(?:amount\s+)?due|payment\s+due\s+date)', re.I)
_CARD_PAYMENT = re.compile(
    r'(payment\s+(?:of\s+)?' + _AMOUNT_CORE + r'.{0,80}?(?:received|credited|successful|has\s+been\s+received)'
    r'.{0,80}?credit\s+card'
    r'|(?:received|credited).{0,40}?payment.{0,80}?credit\s+card'
    r'|credit\s+card.{0,80}?payment\s+(?:of\s+)?' + _AMOUNT_CORE + r'.{0,40}?(?:received|credited|successful))',
    re.I | re.S,
)


def classify(sender: str | None, subject: str | None, body: str | None) -> str:
    """Return one of TXN, STATEMENT, CARD_PAYMENT, IGNORED for an email."""
    text = f'{subject}\n{body}'
    if _STATEMENT_SUBJECT.search(subject or '') and _STATEMENT_BODY.search(body or ''):
        return 'STATEMENT'
    if _CARD_PAYMENT.search(text):
        return 'CARD_PAYMENT'
    if not _AMOUNT_RE.search(text) and not _FOREIGN_AMOUNT_RE.search(text) and not _AMOUNT_SUFFIX_RE.search(text):
        return 'IGNORED'
    if _NOISE.search(text):
        return 'IGNORED'
    if _PAYMENT_RECEIPT_WORDS.search(text) or _DEBIT_WORDS.search(text) or _CREDIT_WORDS.search(text):
        return 'TXN'
    return 'IGNORED'


_CARD_STATEMENT_WORDS = re.compile(r'credit\s*card|card\s+(?:ending|no\.?|number)|card\s+statement', re.I)


def looks_like_card_statement(subject: str | None, body: str | None, has_pdf: bool) -> bool:
    """A credit-card statement email whose totals live only in the attached PDF."""
    return bool(
        has_pdf
        and _STATEMENT_SUBJECT.search(subject or '')
        and _CARD_STATEMENT_WORDS.search(f'{subject}\n{body}')
    )


def _direction(text: str) -> str:
    """Determine DEBIT vs CREDIT. Bulletproofed against misleading 'received order' phrases."""
    # 1. Purchase/bill payment receipt ("we have received your payment of Rs 500 for Google Cloud") -> DEBIT
    if _PAYMENT_RECEIPT_WORDS.search(text):
        if not re.search(r'\b(refund\s+receipt|money\s+received\s+from|received\s+from)\b', text, re.I):
            return 'DEBIT'

    # 2. Explicit credit indicators (refund, cashback, credited to account, salary)
    has_explicit_credit = bool(_CREDIT_EXPLICIT_RE.search(text))
    # 3. Explicit debit indicators (debited from account, spent at, charged to)
    has_explicit_debit = bool(_DEBIT_EXPLICIT_RE.search(text))

    if has_explicit_debit and not has_explicit_credit:
        return 'DEBIT'
    if has_explicit_credit and not has_explicit_debit:
        return 'CREDIT'

    # 4. Proximity & priority fallback
    debit = _DEBIT_WORDS.search(text)
    credit = _CREDIT_WORDS.search(text)
    if debit and credit:
        return 'DEBIT' if debit.start() <= credit.start() else 'CREDIT'
    return 'CREDIT' if credit and not debit else 'DEBIT'


# ---------------------------------------------------------------------------
# Field Extractors (Dates, Times, Instruments, Accounts)
# ---------------------------------------------------------------------------

_MONTHS = {
    m: i for i, m in enumerate(
        ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'],
        start=1,
    )
}

_DATE_PATTERNS = [
    # 2025-10-05 or 2025/10/05
    (re.compile(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b'), 'ymd'),
    # 05-10-2025, 05/10/25, 05.10.25
    (re.compile(r'\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b'), 'dmy'),
    # 05-Oct-25, 5th Oct 2025, 05Oct25, 5-OCT-2025, 5th October 2025
    (re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)?[-\s]?([A-Za-z]{3})[a-z]*[-\s,]*(\d{2,4})\b', re.I), 'dMy'),
    # Oct 05, 2025 or October 5th, 2025
    (re.compile(r'\b([A-Za-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b', re.I), 'Mdy'),
]


def _year(y: str | int) -> int:
    val = int(y)
    return val + 2000 if val < 100 else val


def parse_date(text: str | None, reference: datetime.date | None = None) -> datetime.date | None:
    """Extract first plausible calendar date. With a reference date, rejects dates > 60 days away."""
    if not text:
        return None
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(text):
            try:
                if kind == 'ymd':
                    d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif kind == 'dmy':
                    d = datetime.date(_year(m.group(3)), int(m.group(2)), int(m.group(1)))
                elif kind == 'dMy':
                    mon = _MONTHS.get(m.group(2).lower()[:3])
                    if not mon:
                        continue
                    d = datetime.date(_year(m.group(3)), mon, int(m.group(1)))
                else:
                    mon = _MONTHS.get(m.group(1).lower()[:3])
                    if not mon:
                        continue
                    d = datetime.date(int(m.group(3)), mon, int(m.group(2)))
            except ValueError:
                continue
            if reference and abs((d - reference).days) > 60:
                continue
            return d
    return None


_TIME_RE = re.compile(r'\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*([AaPp][Mm])?\b')


def parse_time(text: str | None) -> datetime.time | None:
    """Extract transaction time if present in the alert string."""
    m = _TIME_RE.search(text or '')
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    meridiem = (m.group(4) or '').lower()
    if meridiem == 'pm' and hour < 12:
        hour += 12
    elif meridiem == 'am' and hour == 12:
        hour = 0
    return datetime.time(hour, minute, int(m.group(3) or 0))


_LAST4_PATTERNS = [
    re.compile(r'ending\s*(?:with|in)?\s*(?:[xX*•.]+\s?)?(\d{4})(?!\d)', re.I),
    re.compile(r'(?:[xX*•]{2,}|\.{3,})[\s\-]*(\d{4})(?!\d)'),
    re.compile(r'\b(?:a/c|ac|acct|account|card)\s*(?:no\.?|number)?\s*[:\-]?\s*[\dxX*•\s\-]*[xX*•]+[\s\-]*(\d{4})(?!\d)', re.I),
    re.compile(r'\b(?:a/c|ac|acct|account|card)\s*(?:no\.?|number)?\s*[:\-]?\s*[xX*•]*\s?(\d{4})(?!\d)', re.I),
]


def parse_last4(text: str | None) -> str:
    """Extract the last 4 digits of the card or bank account from alert text."""
    for rx in _LAST4_PATTERNS:
        m = rx.search(text or '')
        if m:
            return m.group(1)
    return ''


def parse_instrument(text: str | None) -> str:
    """Identify payment instrument: CREDIT_CARD, DEBIT_CARD, BANK_ACCOUNT, UPI, OTHER."""
    t = (text or '').lower()
    if 'credit card' in t or re.search(r'av(?:ai)?l(?:able|\.)?\s*(?:credit\s*)?l(?:imi)?t|avl\s*lmt', t):
        return 'CREDIT_CARD'
    if 'debit card' in t:
        return 'DEBIT_CARD'
    if re.search(r'(\ba/c\b|\bac\b|\bacct\b|\baccount\b|\bsavings\b)', t):
        return 'BANK_ACCOUNT'
    if re.search(r'\b(?:card\s*(?:ending|no|number)|credit\s*card)\b', t):
        return 'CREDIT_CARD'
    if re.search(r'\b(upi|vpa|wallet)\b', t):
        return 'UPI'
    return 'OTHER'


def parse_channel(text: str | None, instrument: str) -> str:
    """Identify payment channel: UPI, ATM, IMPS, AUTO_DEBIT, NETBANKING, CARD, OTHER."""
    t = (text or '').lower()
    if re.search(r'\b(upi|vpa)\b|@[a-z]{2,}\b', t):
        return 'UPI'
    if re.search(r'\b(atm|cash\s+wdl|cash\s+withdrawal|nfs\*cash)\b', t):
        return 'ATM'
    if re.search(r'\b(imps|neft|rtgs)\b', t):
        return 'IMPS'
    if re.search(r'\b(nach|ecs|auto[\s-]?debit|si\s+debit|standing\s+instruction|mandate)\b', t):
        return 'AUTO_DEBIT'
    if re.search(r'net\s*banking|netbanking|billdesk|payu', t):
        return 'NETBANKING'
    if instrument in ('CREDIT_CARD', 'DEBIT_CARD') or re.search(r'\b(pos|swipe|ecom)\b', t):
        return 'CARD'
    return 'OTHER'


_REF_RE = re.compile(
    r'(?:upi\s*ref(?:erence)?|ref(?:erence)?|rrn|txn\s*id|transaction\s*id|utr|order\s*id)\.?\s*(?:no\.?|number|#|id)?'
    r'\s*(?:is)?\s*[:\-]?\s*([A-Za-z0-9_\-]{6,28})',
    re.I,
)


def parse_reference(text: str | None) -> str:
    """Extract unique transaction reference / UTR / RRN / Order ID."""
    m = _REF_RE.search(text or '')
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# Merchant Parsing & Normalization
# ---------------------------------------------------------------------------

_STOP = (
    r'(?=\s+on\s+\d|\s+on\s+[A-Za-z]{3}\s+\d|\s+on\s+your\b|\s+using\b|\s*\.\s|\s*\.$'
    r'|\s+avl|\s+avbl|\s+available|\s+ref\b|\s+upi\b|\s+via\b|\s+for\s+inr|\s*\(|\s*,\s*(?:avl|ref)'
    r'|\s+total\s+avbl|\s+bal\b|\s+balance\b|\s+clear\s+bal\b|\s+eff\s+bal\b|\s+throug?h\b'
    r'|\s+with\s+(?:ref|rrn|txn|utr)\b|\s+dated\b|\s+if\s+not\b|\s+not\s+you\b|\s+call\s+1800\b'
    r'|\s+sms\s+block\b|\s+toll\s*free\b|\n|$)'
)

_MERCHANT_PATTERNS = [
    # UPI with real name in parentheses: "to VPA swiggy@icici (Swiggy)" / "to user@upi (Ramesh Kumar)"
    re.compile(r'\b(?:to|by|from)\s+(?:vpa\s+)?\S+@[a-z0-9._\-]+\s*\(([^)]{2,60})\)', re.I),
    # HDFC UPI: "to VPA abc@okicici MERCHANT NAME on 05-10-25" / credits "by VPA x@okhdfc NAME on"
    re.compile(r'\b(?:to|by|from)\s+vpa\s+(\S+@\S+?)\s+(.{2,60}?)' + _STOP, re.I),
    re.compile(r'\b(?:to|by|from)\s+vpa\s+(\S+@[a-z]{2,})', re.I),
    # "to abc@ybl on" / "to paytm.s1h22ek@pty SUBXTR RUZZ on"
    re.compile(r'\bto\s+([a-z0-9._\-]+@[a-z]{2,})\s+([A-Z][A-Za-z0-9 &.\'\-]{1,60}?)' + _STOP, re.I),
    re.compile(r'\bto\s+([a-z0-9._\-]+@[a-z]{2,})\b', re.I),
    # Axis summary: "Merchant Name: AMAZON"
    re.compile(r'merchant\s*(?:name)?\s*[:\-]\s*(.{2,60}?)' + _STOP, re.I),
    # ICICI: "on 05-Oct-25 on AMAZON. Avl Limit"; "on 05-Oct-25 at AMAZON"
    re.compile(
        r'\bon\s+\d{1,2}[-/\s][A-Za-z0-9]{2,3}[-/\s]\d{2,4}(?:[\s,:]+\d{1,2}:\d{2}(?::\d{2})?)?\s+(?:on|at)\s+(.{2,60}?)'
        + _STOP,
        re.I,
    ),
    # HDFC / SBI card: "at AMAZON on 05-10-25"
    re.compile(r'\bat\s+(.{2,60}?)' + _STOP, re.I),
    # HDFC: "towards MERCHANT"
    re.compile(r'\btowards\s+(.{2,60}?)' + _STOP, re.I),
    # ICICI / Axis: "Info: UPI-12345-MERCHANT" / "Info: AMAZON"
    re.compile(r'\binfo\s*[:\-]\s*(.{2,80}?)' + _STOP, re.I),
    # Axis: "UPI/P2M/123456/MERCHANT"
    re.compile(r'\b(?:UPI|IMPS|NEFT)/(?:P2[AM]/)?\d+/([^/\s]{2,40})', re.I),
    # SBI / Kotak: "transfer to MERCHANT Ref No"
    re.compile(r'\btransfer(?:red)?\s+to\s+(.{2,60}?)' + _STOP, re.I),
    # Kotak: "Sent Rs.500 from Kotak Bank AC X1234 to MERCHANT on"
    re.compile(r'\b(?:sent|paid)\s+to\s+([A-Z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP, re.I),
    re.compile(r'\bto\s+([A-Z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP),
    # Credits: "received from NAME", "from NAME on", "credited by NAME"
    re.compile(r'\bfrom\s+([A-Za-z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP, re.I),
    re.compile(r'\b(?:from|by)\s+([A-Za-z][A-Za-z0-9 &.\'\-]{2,60}?)' + _STOP, re.I),
]

_BAD_MERCHANT = re.compile(
    r'^(your\b|the\b|a/c|ac\b|account|card\b|credit\b|debit\b|bank\b|hdfc|icici|sbi\b|axis|kotak|customer'
    r'|xx|on\s|rs\b|inr\b|\d)',
    re.I,
)


def parse_merchant(text: str | None) -> tuple[str, str]:
    """Extract raw merchant string and supporting context from alert text."""
    for rx in _MERCHANT_PATTERNS:
        for m in rx.finditer(text or ''):
            groups = [g for g in m.groups() if g]
            if not groups:
                continue
            candidate = groups[-1].strip(' .,:-')
            if len(groups) >= 2 and len(candidate) < 3:
                candidate = groups[0]
            if len(candidate) < 2 or _BAD_MERCHANT.match(candidate):
                continue
            return candidate[:120], ' '.join(groups)[:255]
    return '', ''


class _KnownBrandsProxy(dict):
    """Dynamic dictionary proxy pulling from BrandKnowledge in database for backward compatibility."""

    def __getitem__(self, key: str) -> tuple[str, str, str]:
        from .knowledge import lookup_brand

        val = lookup_brand(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key: object) -> bool:
        from .knowledge import lookup_brand

        return lookup_brand(str(key)) is not None

    def get(self, key: str, default: object = None) -> object:
        from .knowledge import lookup_brand

        val = lookup_brand(key)
        return val if val is not None else default


KNOWN_BRANDS = _KnownBrandsProxy()


class _CategoryKeywordsProxy(list):
    """Dynamic list proxy pulling from KeywordKnowledge in database for backward compatibility."""

    def __iter__(self):
        from .knowledge import get_keyword_rules

        return iter(get_keyword_rules())

    def __len__(self) -> int:
        from .knowledge import get_keyword_rules

        return len(get_keyword_rules())


CATEGORY_KEYWORDS = _CategoryKeywordsProxy()

_VPA_NOISE = re.compile(
    r'^(paytmqr|paytm|bharatpe|q\d+|gpay|phonepe|mab|ombk|upi|pay|bhim)[._\-]*',
    re.I,
)
_MERCHANT_NOISE = re.compile(
    r'\b(upi|pos|ecom|imps|neft|rtgs|p2m|p2a|pvt|private|ltd|limited|llp|india|in|inc|co|corp|the|www|com|payments?)\b',
    re.I,
)


def normalize_merchant(raw: str | None) -> tuple[str, str]:
    """Return (display_name, merchant_key). The key is stable across alert formats for learning."""
    s = (raw or '').strip()
    if not s:
        return '', ''
    if '@' in s and ' ' not in s.strip():
        s = _VPA_NOISE.sub('', s.split('@')[0])
        s = re.sub(r'[._\-]+', ' ', s)
    s = re.sub(r'\b\d{3,}\b', ' ', s)
    s = re.sub(r'[*#/|_]+', ' ', s)
    cleaned = re.sub(r'\s+', ' ', _MERCHANT_NOISE.sub(' ', s)).strip(' .,-')
    cleaned = re.sub(r'^(?:from|to|by|at)\s+', '', cleaned, flags=re.I)
    key = re.sub(r'[^A-Z0-9]', '', (cleaned or s).upper())[:60]

    from .knowledge import get_brand_tokens, lookup_brand

    # 1. Direct match in BrandKnowledge (cached DB catalog)
    match = lookup_brand(key)
    if match:
        return match[0], key

    # 2. Substring token match against known brands in database
    words = _words(cleaned or s)
    for token in get_brand_tokens():
        if _token_hit(token, key, words):
            tmatch = lookup_brand(token)
            if tmatch:
                return tmatch[0], token

    display = (cleaned or s).strip()
    if display.isupper() or display.islower():
        display = display.title()
    return display[:120], key


_SHORT_TOKEN = 4


def _words(text: str) -> set[str]:
    return set(re.findall(r'[A-Z0-9]+', (text or '').upper()))


def _token_hit(token: str, key: str, words: set[str]) -> bool:
    if len(token) <= _SHORT_TOKEN:
        return token in words or key == token
    return token in key


def brand_category(merchant_key: str, text: str = '') -> str | None:
    """Resolve category name from BrandKnowledge or KeywordKnowledge in database."""
    from .knowledge import get_keyword_rules, lookup_brand

    match = lookup_brand(merchant_key)
    if match:
        return match[1]
    words = _words(text)
    for item in get_keyword_rules():
        if _token_hit(item[0], merchant_key, words):
            return item[1]
    return None


def brand_icon(merchant_key: str, text: str = '') -> str | None:
    """Return specific Material Symbols icon for a known merchant brand or keyword."""
    from .knowledge import get_keyword_rules, lookup_brand

    match = lookup_brand(merchant_key)
    if match and len(match) > 2:
        return match[2]
    words = _words(text)
    for item in get_keyword_rules():
        if len(item) > 2 and _token_hit(item[0], merchant_key, words):
            return item[2]
    return None


def parse_emi_details(raw: str | None) -> dict[str, Any]:
    """Parse EMI components from bank statement line or email alert text.

    Returns dict with keys:
      is_emi: bool
      component: 'PRINCIPAL' | 'INTEREST' | 'PURCHASE' | ''
      installment_num: int | None
      total_installments: int | None
      reference: str
      merchant: str
    """
    if not raw:
        return {'is_emi': False, 'component': '', 'installment_num': None, 'total_installments': None, 'reference': '', 'merchant': ''}

    s = raw.strip()
    # 1. HDFC / Indian statement installment patterns:
    # OFFUS EMI,PRIN NB:03,XXXXXXXXXX9861 or EMI,PRIN NB:03
    prin_match = re.search(r'\b(?:OFFUS\s+)?EMI\s*,\s*PRIN\s+NB:(\d+)\s*,\s*([A-Za-z0-9]+)', s, re.I)
    if prin_match:
        ref = prin_match.group(2)[-4:]
        num = int(prin_match.group(1))
        return {
            'is_emi': True,
            'component': 'PRINCIPAL',
            'installment_num': num,
            'total_installments': None,
            'reference': ref,
            'merchant': f'Loan ••{ref} (Principal #{num})',
        }

    # 2. OFFUS EMI,INT NBR:03,XXXXXXXXXX9861 or EMI,INT NBR:03
    int_match = re.search(r'\b(?:OFFUS\s+)?EMI\s*,\s*INT\s+NBR:(\d+)\s*,\s*([A-Za-z0-9]+)', s, re.I)
    if int_match:
        ref = int_match.group(2)[-4:]
        num = int(int_match.group(1))
        return {
            'is_emi': True,
            'component': 'INTEREST',
            'installment_num': num,
            'total_installments': None,
            'reference': ref,
            'merchant': f'Loan ••{ref} (Interest #{num})',
        }

    # 3. Standard installment pattern: EMI (MONTH|INSTALMENT|INSTALLMENT)? (\d+)\s*(?:OF|/)\s*(\d+)
    inst_match = re.search(r'\b(?:EMI|INSTALLMENT|INSTALMENT)\s*(?:MONTH)?\s*(\d+)\s*(?:OF|/)\s*(\d+)', s, re.I)
    if inst_match:
        cur, tot = int(inst_match.group(1)), int(inst_match.group(2))
        return {
            'is_emi': True,
            'component': 'PRINCIPAL',
            'installment_num': cur,
            'total_installments': tot,
            'reference': '',
            'merchant': f'EMI Installment ({cur}/{tot})',
        }

    # 4. Merchant purchase on EMI: EMI <Merchant> or <Merchant> EMI or SMARTEMI or FLEXIPAY
    if re.search(r'^(?:EMI\s+|OFFUS\s+EMI\s+|SMARTEMI\s+|FLEXIPAY\s+)', s, re.I) or re.search(r'\b(?:NO\s+COST\s+EMI|SMARTEMI|FLEXIPAY)\b', s, re.I):
        clean_m = re.sub(r'^(?:EMI|OFFUS\s+EMI|SMARTEMI|FLEXIPAY)\s+', '', s, flags=re.I).strip()
        clean_m = re.sub(r'^(?:UPI-)', '', clean_m, flags=re.I).strip()
        disp, _ = normalize_merchant(clean_m)
        return {
            'is_emi': True,
            'component': 'PURCHASE',
            'installment_num': None,
            'total_installments': None,
            'reference': '',
            'merchant': f'{disp or clean_m} (EMI)',
        }

    return {'is_emi': False, 'component': '', 'installment_num': None, 'total_installments': None, 'reference': '', 'merchant': ''}


# ---------------------------------------------------------------------------
# Public Parse Results
# ---------------------------------------------------------------------------

@dataclass
class ParsedTransaction:
    amount: Decimal
    direction: str
    txn_date: datetime.date
    txn_time: datetime.time | None = None
    merchant: str = ''
    merchant_raw: str = ''
    merchant_key: str = ''
    currency: str = 'INR'
    instrument: str = 'OTHER'
    channel: str = 'OTHER'
    last4: str = ''
    institution: str = ''
    reference: str = ''
    is_emi: bool = False
    emi_reference: str = ''
    emi_installment_num: int | None = None
    emi_total_installments: int | None = None
    emi_component: str = ''
    refunded_amount: Decimal = Decimal('0.00')
    refund_date: datetime.date | None = None


@dataclass
class ParsedStatement:
    institution: str = ''
    last4: str = ''
    statement_date: datetime.date | None = None
    due_date: datetime.date | None = None
    total_due: Decimal | None = None
    min_due: Decimal | None = None
    period_start: datetime.date | None = None
    period_end: datetime.date | None = None
    lines: list = field(default_factory=list)


@dataclass
class ParsedLine:
    txn_date: datetime.date
    description: str
    amount: Decimal
    is_credit: bool = False


def parse_transaction(
    sender: str | None,
    subject: str | None,
    body: str | None,
    received: datetime.datetime | datetime.date | None = None,
) -> ParsedTransaction | None:
    """Parse a single bank or card alert email into a structured ParsedTransaction."""
    text = clean_text(f'{body}')
    full = f'{subject}\n{text}'
    received_date = received.date() if isinstance(received, datetime.datetime) else received

    # 1. Currency & Amount extraction
    currency = 'INR'
    m_txn = _TXN_AMOUNT_RE.search(full)
    m_inr = _AMOUNT_RE.search(full)
    m_foreign = _FOREIGN_AMOUNT_RE.search(full)
    m_suffix = _AMOUNT_SUFFIX_RE.search(full)

    # Prefer explicit transaction-tied amount first to avoid available balance numbers
    if m_txn:
        amount = to_decimal(m_txn.group(1))
    elif m_inr:
        amount = to_decimal(m_inr.group(1))
    elif m_foreign:
        currency = m_foreign.group(1).upper()
        amount = to_decimal(m_foreign.group(2))
    elif m_suffix:
        amount = to_decimal(m_suffix.group(1))
    else:
        amount = None

    if not amount or amount <= 0:
        return None

    # 2. Merchant extraction & normalization
    merchant_text, merchant_raw = parse_merchant(text)
    if not merchant_text:
        merchant_text, merchant_raw = parse_merchant(subject or '')
    display, key = normalize_merchant(merchant_text)

    # 3. Instrument, channel & details
    instrument = parse_instrument(full)
    emi = parse_emi_details(full)
    if emi['is_emi'] and emi['merchant'] and not display:
        display = emi['merchant']

    return ParsedTransaction(
        amount=amount,
        direction=_direction(full),
        txn_date=parse_date(text, received_date) or received_date or datetime.date.today(),
        txn_time=parse_time(text),
        merchant=display,
        merchant_raw=merchant_raw,
        merchant_key=key,
        currency=currency,
        instrument=instrument,
        channel=parse_channel(full, instrument),
        last4=parse_last4(full),
        institution=detect_institution(sender, full),
        reference=parse_reference(text),
        is_emi=emi['is_emi'],
        emi_reference=emi['reference'],
        emi_installment_num=emi['installment_num'],
        emi_total_installments=emi['total_installments'],
        emi_component=emi['component'],
    )


def _labelled_amount(text: str, label: str) -> Decimal | None:
    m = re.search(
        label + r'[^0-9₹\n]{0,40}?(?:' + _AMOUNT_CORE + r'|([0-9][0-9,]*\.[0-9]{2}))',
        text,
        re.I,
    )
    if not m:
        return None
    return to_decimal(m.group(1) or m.group(2))


def _labelled_date(text: str, label: str) -> datetime.date | None:
    m = re.search(label + r'[^0-9A-Za-z\n]{0,15}(.{6,25})', text, re.I)
    return parse_date(m.group(1)) if m else None


def parse_statement_summary(sender: str | None, subject: str | None, text: str | None) -> ParsedStatement:
    """Extract totals, due date, and billing period from a statement email body or PDF plaintext."""
    full = f'{subject}\n{text or ""}'
    st = ParsedStatement(
        institution=detect_institution(sender, full),
        last4=parse_last4(full),
        total_due=_labelled_amount(full, r'total\s+(?:amount\s+)?due'),
        min_due=_labelled_amount(full, r'min(?:imum)?\.?\s+(?:amount\s+)?due'),
        due_date=_labelled_date(full, r'(?:payment\s+)?due\s+(?:date|by|on)'),
        statement_date=_labelled_date(full, r'statement\s+(?:date|generated\s+on)'),
    )
    period = re.search(
        r'(?:statement\s+period|billing\s+(?:period|cycle))[^0-9A-Za-z]{0,10}(.{6,20}?)\s*(?:to|-|–)\s*(.{6,20})',
        full,
        re.I,
    )
    if period:
        st.period_start, st.period_end = parse_date(period.group(1)), parse_date(period.group(2))
    if not st.statement_date and st.period_end:
        st.statement_date = st.period_end
    return st


_LINE_RE = re.compile(
    r'^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s?[A-Za-z]{3}\s?\d{2,4})'
    r'(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?'
    r'\s+(.+?)\s+'
    r'(?:[A-Z]{3}\s+[0-9,]+\.\d{2}\s+)?'
    r'(?:₹\s?|Rs\.?\s?|INR\s?)?(-?\s*[0-9][0-9,]*\.\d{2})\s*(Cr|CR|C|Dr|DR|D)?\s*$'
)
_SKIP_LINE = re.compile(
    r'(opening\s+balance|closing\s+balance|total\s+(?:amount\s+)?due|minimum\s+(?:amount\s+)?due|'
    r'credit\s+limit|available\s+limit|previous\s+balance|reward\s+points)',
    re.I,
)


def parse_statement_lines(text: str | None) -> list[ParsedLine]:
    """Parse line items from statement PDF plaintext. Payment-received lines are marked credit."""
    lines: list[ParsedLine] = []
    for raw in (text or '').splitlines():
        if _SKIP_LINE.search(raw):
            continue
        m = _LINE_RE.match(raw)
        if not m:
            continue
        d = parse_date(m.group(1))
        amount = to_decimal(m.group(3).replace(' ', ''))
        if not d or not amount:
            continue
        desc = re.sub(r'\s+', ' ', m.group(2)).strip()
        is_credit = amount < 0 or (m.group(4) or '').upper().startswith('C') or bool(
            re.search(r'payment\s+received|thank\s+you\s+for\s+(?:the\s+)?payment|refund|reversal', desc, re.I)
        )
        lines.append(ParsedLine(txn_date=d, description=desc[:255], amount=abs(amount), is_credit=is_credit))
    return lines


def parse_card_payment(
    sender: str | None,
    subject: str | None,
    body: str | None,
) -> tuple[Decimal | None, str, str]:
    """Extract (amount, last4, institution) for a 'payment received on your credit card' alert email."""
    full = f'{subject}\n{clean_text(body)}'
    m = _AMOUNT_RE.search(full)
    return (to_decimal(m.group(1)) if m else None), parse_last4(full), detect_institution(sender, full)
