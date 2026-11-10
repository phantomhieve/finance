"""
Shared utilities used by both tracker and portfolio apps.
"""
from __future__ import annotations

import datetime
import os
import re
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

ZERO: Decimal = Decimal('0')
ROUND2: Decimal = Decimal('0.01')


def safe_redirect(request: HttpRequest, fallback: str = 'dashboard') -> HttpResponseRedirect:
    """Redirect to the `next` POST/GET param only if it's a safe, same-host URL."""
    target = request.POST.get('next') or request.GET.get('next', '')
    allowed_hosts = {request.get_host()}
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts=allowed_hosts):
        return redirect(target)
    if fallback and isinstance(fallback, str) and url_has_allowed_host_and_scheme(fallback, allowed_hosts=allowed_hosts):
        return redirect(fallback)
    if fallback and isinstance(fallback, str) and not fallback.startswith(('/', 'http://', 'https://', '//', '\\')):
        try:
            return redirect(fallback)
        except Exception:
            pass
    return redirect('dashboard')


def feature_enabled(user: Any, feature_name: str) -> bool:
    """HouseholdConfig toggle for the user's household; True when there is no group or config."""
    group = getattr(user, 'group', None)
    if group is None:
        return True
    try:
        config = group.config
    except ObjectDoesNotExist:
        return True
    return getattr(config, f'feature_{feature_name}', True)


def fy_start_year(today: datetime.date | None = None) -> int:
    """Return the FY start-year for a date (Apr-Mar cycle)."""
    if today is None:
        today = datetime.date.today()
    return today.year if today.month >= 4 else today.year - 1


def fy_label(fy_start: int) -> str:
    """Format a FY label like 'FY 2025-26'."""
    return f"FY {fy_start}-{str(fy_start + 1)[-2:]}"


_FY_LABEL_RE = re.compile(r'^FY\s*(\d{4})-(\d{2})$')


def fy_start_from_label(label: str | None) -> int | None:
    """Inverse of fy_label: 'FY 2025-26' → 2025. Returns None for blank / 'Long Term' / malformed."""
    m = _FY_LABEL_RE.match((label or '').strip())
    if not m:
        return None
    start = int(m.group(1))
    if (start + 1) % 100 != int(m.group(2)):
        return None
    return start


def pct(part: Any, total: Any) -> Decimal:
    """Percentage with 2-decimal precision; returns ZERO when total is falsy or on conversion error."""
    if not total:
        return ZERO
    try:
        p = Decimal(str(part)) if not isinstance(part, Decimal) else part
        t = Decimal(str(total)) if not isinstance(total, Decimal) else total
        return (p / t * Decimal('100')).quantize(ROUND2)
    except Exception:
        return ZERO


def pnl_pct(pnl: Any, invested: Any) -> Decimal:
    """P&L percentage relative to invested amount."""
    return pct(pnl, invested)


def get_google_credentials_path() -> str:
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


def get_google_credentials(group: Any = None) -> dict[str, Any] | str:
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
            raw = (config.google_credentials_json or '').strip()
            if raw:
                if not raw.startswith('{'):
                    from expenses.crypto import decrypt
                    raw = decrypt(raw).strip()
                if raw:
                    import json as _json
                    return _json.loads(raw)
        except Exception:
            pass  # fall through to global
    return get_google_credentials_path()

