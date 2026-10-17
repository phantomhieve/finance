"""Pydantic data schemas for structured outputs in the expenses AI pipeline."""
from __future__ import annotations

from pydantic import BaseModel


class CategoryChoice(BaseModel):
    """Categorisation prediction for a single transaction item."""
    id: int
    category: str
    confidence: float


class CategoryBatch(BaseModel):
    """Batch of categorisation predictions."""
    results: list[CategoryChoice]


class ExtractedTxn(BaseModel):
    """Transaction extracted from raw email alert text."""
    is_transaction: bool
    amount: float | None = None
    currency: str | None = None
    direction: str | None = None
    date: str | None = None
    merchant: str | None = None
    instrument: str | None = None
    last4: str | None = None


class ExtractedLine(BaseModel):
    """Single line item extracted from a credit card statement."""
    date: str
    description: str
    amount: float
    is_credit: bool


class ExtractedLines(BaseModel):
    """List of extracted statement line items."""
    lines: list[ExtractedLine]


class MonthlyNote(BaseModel):
    """Narrative monthly commentary for household spend email."""
    headline: str
    observations: list[str]


class AnomalyItem(BaseModel):
    """Single transaction anomaly assessment."""
    id: int
    is_suspicious: bool = False
    reasons: list[str] = []
    severity: str = "LOW"


class AnomalyBatchResult(BaseModel):
    """Batch anomaly assessment from AI financial auditor."""
    anomalies: list[AnomalyItem] = []

