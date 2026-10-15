"""System and task prompt builders for expenses AI models."""
from __future__ import annotations

import json
from typing import Any

from ..parsing import mask_sensitive

# ---------------------------------------------------------------------------
# System Prompts
# ---------------------------------------------------------------------------

CATEGORISE_SYSTEM = """\
You categorise Indian household bank and card transactions.
Pick exactly one category per item from the allowed list, spelled exactly as given.
Use the household's own past decisions (examples) as the strongest signal: if a merchant
resembles an example, follow it. UPI payments to a person's name are usually "Transfers"
unless the examples say otherwise. Credit-card bill payments (CRED, BillDesk card payment)
are "Credit Card Payment". SIPs, brokers and mutual funds are "Investments".
confidence is 0-1; use < 0.5 when you are guessing."""

EXTRACT_SYSTEM = """\
You read one Indian bank/card alert email and extract the transaction it reports.
is_transaction is false for OTPs, offers, reminders of future debits, declined or failed
transactions, and statements. direction: DEBIT (money left the account) or CREDIT.
instrument: CREDIT_CARD, DEBIT_CARD, BANK_ACCOUNT or UPI. date: YYYY-MM-DD.
merchant: the payee/merchant as written (null if none). last4: last 4 digits of the
card/account if visible. Never invent values."""

STATEMENT_SYSTEM = """\
Extract every transaction line from this Indian credit card statement.
date as YYYY-MM-DD; is_credit true for payments, refunds and reversals.
Skip totals, balances, reward points and summaries."""

MONTHLY_NOTE_SYSTEM = """\
You write a brief monthly spending note for an Indian household.
Use only numbers in the JSON. headline: one sentence. observations: 2-4 short,
specific, non-judgemental points (biggest changes vs last month, notable merchants,
one practical suggestion). Use ₹ and Indian number formatting."""

ANOMALY_SYSTEM = """\
You are Vault's expert AI financial auditor for Indian personal finance.
Your mission is to detect suspicious, fraudulent, duplicate, or genuinely abnormal transactions in a household's spending.

Flag an expense as suspicious ONLY when there is a clear, actionable reason:
- Possible double charge / billing glitch (same or near-identical amount at the same merchant within a 48h window)
- Drastic spending spike far exceeding the typical norm for that category (e.g. 5x-10x ordinary dining or grocery bill)
- High-value charge at an unfamiliar merchant or merchant with suspicious characteristics
- High-value transaction at unusual hours (midnight to 5 AM) for non-travel services
- Suspicious foreign currency charge when domestic cards are normally used
- Rapid burst of charges on the same card in minutes
- Clear category vs merchant mismatch

Do NOT flag routine recurring expenses (regular rent, utility bills, standard grocery runs, SIPs, normal card payments).
For each suspicious transaction, return `is_suspicious=true` and provide a concise, human-friendly reason explaining why."""


# ---------------------------------------------------------------------------
# User Prompt Builders
# ---------------------------------------------------------------------------

def build_categorise_prompt(
    items: list[dict[str, Any]],
    allowed_categories: set[str] | list[str],
    examples: list[tuple[str, str]],
) -> str:
    """Build structured prompt for batch transaction categorisation."""
    allowed_sorted = sorted(set(allowed_categories))
    return (
        f"Allowed categories: {json.dumps(allowed_sorted)}\n\n"
        f"Household examples (merchant → category): {json.dumps(examples[:40])}\n\n"
        f"Transactions:\n{json.dumps(items, default=str)}"
    )


def build_extract_prompt(subject: str, body: str) -> str:
    """Mask sensitive account numbers and construct extraction prompt."""
    raw = f"Subject: {subject}\n\n{body}"
    return mask_sensitive(raw)[:2500]


def build_statement_prompt(text: str) -> str:
    """Mask and slice statement text for fallback line item extraction."""
    return mask_sensitive(text)[:12000]


def build_monthly_note_prompt(summary_payload: dict[str, Any]) -> str:
    """Serialize summary metrics to JSON for monthly commentary."""
    return json.dumps(summary_payload, default=str)


def build_anomaly_prompt(items: list[dict[str, Any]], context: dict[str, Any]) -> str:
    """Construct prompt for AI anomaly detection with household spending context."""
    return (
        f"Household spending context:\n{json.dumps(context, default=str)}\n\n"
        f"Transactions to audit:\n{json.dumps(items, default=str)}"
    )

