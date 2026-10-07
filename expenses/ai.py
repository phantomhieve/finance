"""Gemini helpers for the expense tracker: batch categorisation, extraction fallback, monthly note.

Every call is optional — without GEMINI_API_KEY (or on any error) callers fall back to rules.
Only merchant names, amounts and masked email text are sent; never full account numbers.
"""
import json
import logging
import os

from pydantic import BaseModel

from portfolio.ai import _MODEL_FAST

from .parsing import mask_sensitive

logger = logging.getLogger(__name__)

MAX_BATCH = 40


def ai_available():
    return bool(os.environ.get('GEMINI_API_KEY'))


def _model():
    return os.environ.get('EXPENSES_GEMINI_MODEL') or _MODEL_FAST


def _generate(prompt, schema, system):
    from google import genai

    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    response = client.models.generate_content(
        model=_model(),
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type='application/json',
            response_schema=schema,
            temperature=0.1,
        ),
    )
    return schema.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Categorisation
# ---------------------------------------------------------------------------

class CategoryChoice(BaseModel):
    id: int
    category: str
    confidence: float


class CategoryBatch(BaseModel):
    results: list[CategoryChoice]


_CATEGORISE_SYSTEM = """\
You categorise Indian household bank and card transactions.
Pick exactly one category per item from the allowed list, spelled exactly as given.
Use the household's own past decisions (examples) as the strongest signal: if a merchant
resembles an example, follow it. UPI payments to a person's name are usually "Transfers"
unless the examples say otherwise. Credit-card bill payments (CRED, BillDesk card payment)
are "Credit Card Payment". SIPs, brokers and mutual funds are "Investments".
confidence is 0-1; use < 0.5 when you are guessing."""


def categorise(items, category_names, examples):
    """items: [{'id', 'merchant', 'raw', 'amount', 'direction', 'channel'}].

    examples: [(merchant_label, category_name)] learned from the household's edits.
    Returns {id: (category_name, confidence)} for valid answers only.
    """
    if not items or not ai_available():
        return {}
    allowed = set(category_names)
    out = {}
    for start in range(0, len(items), MAX_BATCH):
        chunk = items[start:start + MAX_BATCH]
        prompt = (
            f'Allowed categories: {json.dumps(sorted(allowed))}\n\n'
            f'Household examples (merchant → category): {json.dumps(examples[:40])}\n\n'
            f'Transactions:\n{json.dumps(chunk, default=str)}'
        )
        try:
            parsed = _generate(prompt, CategoryBatch, _CATEGORISE_SYSTEM)
        except Exception as exc:
            logger.warning('AI categorisation failed: %s', exc)
            continue
        for r in parsed.results:
            if r.category in allowed:
                out[r.id] = (r.category, max(0.0, min(1.0, r.confidence)))
    return out


# ---------------------------------------------------------------------------
# Extraction fallback
# ---------------------------------------------------------------------------

class ExtractedTxn(BaseModel):
    is_transaction: bool
    amount: float | None = None
    currency: str | None = None
    direction: str | None = None
    date: str | None = None
    merchant: str | None = None
    instrument: str | None = None
    last4: str | None = None


_EXTRACT_SYSTEM = """\
You read one Indian bank/card alert email and extract the transaction it reports.
is_transaction is false for OTPs, offers, reminders of future debits, declined or failed
transactions, and statements. direction: DEBIT (money left the account) or CREDIT.
instrument: CREDIT_CARD, DEBIT_CARD, BANK_ACCOUNT or UPI. date: YYYY-MM-DD.
merchant: the payee/merchant as written (null if none). last4: last 4 digits of the
card/account if visible. Never invent values."""


def extract_transaction(subject, body):
    if not ai_available():
        return None
    text = mask_sensitive(f'Subject: {subject}\n\n{body}')[:2500]
    try:
        result = _generate(text, ExtractedTxn, _EXTRACT_SYSTEM)
    except Exception as exc:
        logger.warning('AI extraction failed: %s', exc)
        return None
    return result if result.is_transaction and result.amount else None


class ExtractedLine(BaseModel):
    date: str
    description: str
    amount: float
    is_credit: bool


class ExtractedLines(BaseModel):
    lines: list[ExtractedLine]


def extract_statement_lines(text):
    """Fallback line-item extraction for statement PDFs the regex can't read."""
    if not ai_available() or not text:
        return []
    try:
        result = _generate(
            mask_sensitive(text)[:12000], ExtractedLines,
            'Extract every transaction line from this Indian credit card statement. '
            'date as YYYY-MM-DD; is_credit true for payments, refunds and reversals. '
            'Skip totals, balances, reward points and summaries.',
        )
    except Exception as exc:
        logger.warning('AI statement extraction failed: %s', exc)
        return []
    return result.lines


# ---------------------------------------------------------------------------
# Monthly commentary
# ---------------------------------------------------------------------------

class MonthlyNote(BaseModel):
    headline: str
    observations: list[str]


def monthly_commentary(summary_payload):
    """Short, grounded commentary for the monthly email. Returns dict or None."""
    if not ai_available():
        return None
    try:
        note = _generate(
            json.dumps(summary_payload, default=str),
            MonthlyNote,
            'You write a brief monthly spending note for an Indian household. '
            'Use only numbers in the JSON. headline: one sentence. observations: 2-4 short, '
            'specific, non-judgemental points (biggest changes vs last month, notable merchants, '
            'one practical suggestion). Use ₹ and Indian number formatting.',
        )
    except Exception as exc:
        logger.warning('AI monthly commentary failed: %s', exc)
        return None
    return note.model_dump()
