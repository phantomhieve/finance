"""
Shared utilities used by both tracker and portfolio apps.
"""
import datetime
from decimal import Decimal

from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

ZERO = Decimal('0')
ROUND2 = Decimal('0.01')


def safe_redirect(request, fallback='dashboard'):
    """Redirect to the `next` POST param only if it's a safe, same-host URL."""
    target = request.POST.get('next', '')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(fallback)


def fy_start_year(today=None):
    """Return the FY start-year for a date (Apr-Mar cycle)."""
    if today is None:
        today = datetime.date.today()
    return today.year if today.month >= 4 else today.year - 1


def fy_label(fy_start):
    """Format a FY label like 'FY 2025-26'."""
    return f"FY {fy_start}-{str(fy_start + 1)[-2:]}"


def pct(part, total):
    """Percentage with 2-decimal precision; returns ZERO when total is falsy."""
    return (part / total * 100).quantize(ROUND2) if total else ZERO


def pnl_pct(pnl, invested):
    """P&L percentage relative to invested amount."""
    return pct(pnl, invested)


def get_google_credentials_path():
    """Resolve Google service account credentials path from settings or default."""
    path = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS', None)
    if not path:
        path = str(settings.BASE_DIR / 'credentials' / 'google-service-account.json')
    return str(path)
