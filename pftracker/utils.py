"""
Shared utilities used by both tracker and portfolio apps.
"""
import datetime
import os
import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

ZERO = Decimal('0')
ROUND2 = Decimal('0.01')


def safe_redirect(request, fallback='dashboard'):
    """Redirect to the `next` POST/GET param only if it's a safe, same-host URL."""
    target = request.POST.get('next') or request.GET.get('next', '')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect(fallback)



def feature_enabled(user, feature_name):
    """HouseholdConfig toggle for the user's household; True when there is no group or config."""
    group = getattr(user, 'group', None)
    if group is None:
        return True
    try:
        config = group.config
    except ObjectDoesNotExist:
        return True
    return getattr(config, f'feature_{feature_name}', True)


def fy_start_year(today=None):
    """Return the FY start-year for a date (Apr-Mar cycle)."""
    if today is None:
        today = datetime.date.today()
    return today.year if today.month >= 4 else today.year - 1


def fy_label(fy_start):
    """Format a FY label like 'FY 2025-26'."""
    return f"FY {fy_start}-{str(fy_start + 1)[-2:]}"


_FY_LABEL_RE = re.compile(r'^FY\s*(\d{4})-(\d{2})$')


def fy_start_from_label(label):
    """Inverse of fy_label: 'FY 2025-26' → 2025. Returns None for blank / 'Long Term' / malformed."""
    m = _FY_LABEL_RE.match((label or '').strip())
    if not m:
        return None
    start = int(m.group(1))
    if (start + 1) % 100 != int(m.group(2)):
        return None
    return start


def pct(part, total):
    """Percentage with 2-decimal precision; returns ZERO when total is falsy."""
    return (part / total * 100).quantize(ROUND2) if total else ZERO


def pnl_pct(pnl, invested):
    """P&L percentage relative to invested amount."""
    return pct(pnl, invested)


def get_google_credentials_path():
    """Resolve Google service account JSON path from env (GOOGLE_SHEETS_CREDENTIALS)."""
    path = (
        getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS', '')
        or os.environ.get('GOOGLE_SHEETS_CREDENTIALS', '')
        or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
    )
    if not path:
        raise ValueError(
            'Set GOOGLE_SHEETS_CREDENTIALS (or GOOGLE_APPLICATION_CREDENTIALS) '
            'to the path of your service account JSON file.'
        )
    return str(path)


def get_google_credentials(group=None):
    """Resolve Google service account credentials for a household group.

    Resolution order:
    1. group.config.google_credentials_json (if group has per-household creds)
    2. Global GOOGLE_SHEETS_CREDENTIALS env var (fallback)

    Returns:
        dict or str: parsed JSON dict if from DB, file path string if from env.
    """
    if group:
        try:
            config = group.config
            if config.google_credentials_json and config.google_credentials_json.strip():
                import json as _json
                return _json.loads(config.google_credentials_json)
        except Exception:
            pass  # fall through to global
    return get_google_credentials_path()

