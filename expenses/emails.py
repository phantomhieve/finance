"""Context builders and recipients for the expense emails (monthly household summary, bill reminders)."""
import os

from django.urls import reverse
from django.utils import timezone

from portfolio.emails import app_url
from portfolio.templatetags.indian_format import inr

from . import ai
from .services import month_summary, shift_month
from .statements import upcoming_dues

MAX_FLAGGED = 12


def recipients(group):
    """Every adult household member with an email; VAULT_REPORT_EMAIL as a fallback."""
    emails = sorted({
        u.email.strip().lower()
        for u in group.members.filter(user_type__in=('PRIMARY', 'ACCOUNT_HOLDER'), is_active=True)
        if u.email and u.email.strip()
    })
    if not emails:
        fallback = os.environ.get('VAULT_REPORT_EMAIL', '').strip()
        emails = [fallback] if fallback else []
    return emails


def previous_month(today=None):
    today = today or timezone.localdate()
    return shift_month(today.year, today.month, -1)


def _ai_payload(summary):
    return {
        'month': summary['label'],
        'total_spend': summary['total'],
        'previous_month_spend': summary['prev_total'],
        'change_pct': summary['delta_pct'],
        'transactions': summary['count'],
        'categories': [{'name': c['name'], 'amount': c['total'], 'last_month': c['prev'], 'count': c['count']}
                       for c in summary['categories'][:10]],
        'top_merchants': [{'name': m['merchant'], 'amount': m['total'], 'count': m['count']}
                          for m in summary['merchants'][:6]],
        'by_member': [{'name': m['name'], 'amount': m['total']} for m in summary['members']],
        'flagged_count': len(summary['flagged']),
    }


def build_summary_context(group, year, month, with_ai=True):
    """Household spend for one month, counting only transactions detected from mail (alerts + statements)."""
    # Sent to every member, so investment debits (portfolio-only data) are left out.
    summary = month_summary(group, year, month, mail_only=True, hide_investments=True)
    flagged = [e for e in summary['flagged'] if not e.flag_reviewed and e.source != 'MANUAL']
    top_cat = max((c['total'] for c in summary['categories']), default=0)
    for c in summary['categories']:
        c['bar'] = round(c['total'] / top_cat * 100) if top_cat else 0
    movers = sorted((c for c in summary['categories'] if c['prev'] and abs(c['delta']) >= 500),
                    key=lambda c: abs(c['delta']), reverse=True)[:3]
    commentary = ai.monthly_commentary(_ai_payload(summary)) if with_ai and summary['count'] else None
    path = f"{reverse('expenses_home')}?m={year:04d}-{month:02d}"
    return {
        'summary': summary,
        'month': summary['label'],
        'flagged': flagged[:MAX_FLAGGED],
        'flagged_more': max(0, len(flagged) - MAX_FLAGGED),
        'movers': movers,
        'dues': upcoming_dues(group, timezone.localdate(), horizon_days=14),
        'commentary': commentary,
        'as_of': timezone.localtime().strftime('%d %b %Y'),
        'app_url': app_url(path),
        'flagged_url': app_url(path + '&flagged=1'),
    }


def summary_text(ctx):
    s = ctx['summary']
    lines = [f"Household spend — {ctx['month']}", '', f"Total: {inr(s['total'])} ({s['count']} transactions)"]
    if s['delta_pct'] is not None:
        lines.append(f"vs last month: {'+' if s['delta'] > 0 else ''}{s['delta_pct']}%")
    lines.append('')
    for c in s['categories'][:8]:
        lines.append(f"  {c['name']}: {inr(c['total'])}")
    if ctx['flagged']:
        lines += ['', f"{len(ctx['flagged'])} transaction(s) look unusual:"]
        for e in ctx['flagged']:
            lines.append(f"  {e.txn_date:%d %b} {e.merchant} {inr(e.amount)} — {'; '.join(e.flag_reasons or [])}")
    if ctx['commentary']:
        lines += ['', ctx['commentary']['headline']] + [f"  • {o}" for o in ctx['commentary']['observations']]
    if ctx['app_url']:
        lines += ['', ctx['app_url']]
    return '\n'.join(lines)


def build_reminder_context(statement, days_left):
    return {
        'statement': statement,
        'card': statement.payment_source.display_name,
        'days_left': days_left,
        'overdue': days_left < 0,
        'app_url': app_url(reverse('expenses_statement_detail', args=[statement.pk])),
    }
