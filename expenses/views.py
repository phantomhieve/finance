import logging
import secrets
from functools import wraps
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pftracker.utils import feature_enabled, fy_start_year, safe_redirect
from portfolio.emails import app_url
from tracker.services import parse_fy_param

from . import crypto, gmail
from .anomaly import ai_audit_expenses, apply_flags, audit_cooldown_status
from .forms import CategoryForm, ExpenseForm, PaymentSourceForm, StatementUploadForm
from .models import CardStatement, Expense, ExpenseCategory, GmailAccount, MerchantRule, PaymentSource, StatementLine
from .services import (
    INVESTMENT_CATEGORY, available_fys, ensure_default_categories, fy_summary, learn_category,
    manual_merchant, month_summary, monthly_trend, shift_month,
)
from .statements import read_pdf, reconcile, resolve_line, upcoming_dues
from .sync import sync_account

logger = logging.getLogger(__name__)

INLINE_SYNC_SECONDS = 20
_OAUTH_STATE_KEY = 'expenses_gmail_oauth_state'


def _require_expenses(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not getattr(request.user, 'can_view_expenses', False):
            return HttpResponseForbidden('You do not have permission to view this page.')
        if request.user.group is None or not feature_enabled(request.user, 'expenses'):
            raise Http404
        return view_func(request, *args, **kwargs)
    return _wrapped


def _group(request):
    return request.user.group


def _hides_investments(request):
    return not getattr(request.user, 'can_view_portfolio', False)


def _expenses(request):
    """The household's expenses this user may see (investment debits are portfolio-only)."""
    qs = Expense.objects.filter(group=_group(request))
    if _hides_investments(request):
        qs = qs.exclude(category__name=INVESTMENT_CATEGORY)
    return qs


def _form_errors(form):
    return '; '.join(
        f"{(form.fields[f].label or f.replace('_', ' ').capitalize()) if f in form.fields else 'Form'}: {', '.join(e)}"
        for f, e in form.errors.items()
    )


def _parse_month(raw, today):
    try:
        y, m = (int(x) for x in (raw or '').split('-'))
        if 2000 <= y <= 2099 and 1 <= m <= 12:
            return y, m
    except ValueError:
        pass
    return today.year, today.month


def _expense_payload(e):
    return {
        'id': e.pk, 'amount': str(e.amount), 'direction': e.direction, 'txn_date': e.txn_date.isoformat(),
        'merchant': e.merchant, 'category': e.category_id or '', 'payment_source': e.payment_source_id or '',
        'member': e.member_id or '', 'notes': e.notes, 'source': e.get_source_display(),
        'category_source': e.get_category_source_display(), 'raw': e.merchant_raw,
        'subject': e.email_subject, 'flag_reasons': e.flag_reasons or [],
        'flagged': e.needs_review, 'reviewed': e.flag_reviewed,
        'is_refunded': e.is_refunded, 'is_fully_refunded': e.is_fully_refunded,
        'refunded_amount': str(e.refunded_amount),
        'refund_date': e.refund_date.isoformat() if e.refund_date else '',
        'net_amount': str(e.net_amount),
        'is_emi': e.is_emi, 'emi_reference': e.emi_reference,
        'emi_installment_num': e.emi_installment_num, 'emi_component': e.emi_component,
        'edit_url': reverse('expense_edit', args=[e.pk]), 'delete_url': reverse('expense_delete', args=[e.pk]),
        'review_url': reverse('expense_review', args=[e.pk]),
    }


# ---------------------------------------------------------------------------
# Month / year views
# ---------------------------------------------------------------------------

@_require_expenses
def expenses_home(request):
    group = _group(request)
    ensure_default_categories(group)
    today = timezone.localdate()
    year, month = _parse_month(request.GET.get('m'), today)
    summary = month_summary(group, year, month, hide_investments=_hides_investments(request))

    f_cat = request.GET.get('cat', '')
    f_member = request.GET.get('member', '')
    f_source = request.GET.get('source', '')
    f_flagged = request.GET.get('flagged') == '1'
    f_refunds = request.GET.get('refunds') == '1'
    f_emis = request.GET.get('emis') == '1'
    f_query = request.GET.get('q', '').strip()

    qs = (_expenses(request).filter(is_deleted=False, refund_of__isnull=True, txn_date__gte=summary['start'], txn_date__lte=summary['end'])
          .select_related('category', 'payment_source', 'member'))
    if f_cat == 'none':
        qs = qs.filter(category__isnull=True)
    elif f_cat.isdigit():
        qs = qs.filter(category_id=int(f_cat))
    if f_member.isdigit():
        qs = qs.filter(member_id=int(f_member))
    if f_source in ('EMAIL', 'STATEMENT', 'MANUAL'):
        qs = qs.filter(source=f_source)
    if f_flagged:
        qs = qs.filter(is_flagged=True, flag_reviewed=False)
    if f_refunds:
        qs = qs.filter(Q(refunded_amount__gt=0) | Q(refund_date__isnull=False) | Q(direction='CREDIT'))
    if f_emis:
        qs = qs.filter(is_emi=True)
    if f_query:
        qs = qs.filter(Q(merchant__icontains=f_query) | Q(notes__icontains=f_query) | Q(merchant_raw__icontains=f_query))
    rows = list(qs)
    days = [{'date': d, 'items': list(items)} for d, items in groupby(rows, key=lambda e: e.txn_date)]
    for day in days:
        day['spend'] = sum((e.net_amount for e in day['items'] if e.is_spend and e.currency == 'INR'), 0)

    py, pm = shift_month(year, month, -1)
    ny, nm = shift_month(year, month, 1)
    accounts = list(GmailAccount.objects.filter(group=group))
    categories = ExpenseCategory.objects.filter(group=group)
    if _hides_investments(request):
        categories = categories.exclude(name=INVESTMENT_CATEGORY)
    categories = list(categories)
    dues = upcoming_dues(group, today)
    for st in dues:
        st.days_left = (st.due_date - today).days
    context_reconnect = [a for a in accounts if a.needs_reconnect]
    pending_passwords = CardStatement.objects.filter(group=group, status='NEEDS_PASSWORD').count()
    trend = monthly_trend(group, year, month, today=today)
    context = {
        'summary': summary,
        'days': days,
        'row_count': len(rows),
        'payload': {str(e.pk): _expense_payload(e) for e in rows},
        'month_param': f'{year:04d}-{month:02d}',
        'prev_month': f'{py:04d}-{pm:02d}',
        'next_month': f'{ny:04d}-{nm:02d}' if (ny, nm) <= (today.year, today.month) else '',
        'is_current_month': (year, month) == (today.year, today.month),
        'fy_start': fy_start_year(summary['start']),
        'categories': categories,
        'payment_sources': PaymentSource.objects.filter(group=group),
        'members': group.members.filter(user_type__in=('PRIMARY', 'ACCOUNT_HOLDER')),
        'accounts': accounts,
        'reconnect_needed': context_reconnect,
        'dues': dues,
        'pending_passwords': pending_passwords,
        'f_cat': f_cat, 'f_member': f_member, 'f_source': f_source, 'f_flagged': f_flagged,
        'f_refunds': f_refunds, 'f_emis': f_emis, 'f_query': f_query,
        'is_filtered': bool(f_cat or f_member or f_source or f_flagged or f_refunds or f_emis or f_query),
        'today': today,
        'trend': trend,
        'open_flags': sum(1 for e in summary['flagged'] if not e.flag_reviewed),
        'attention_count': len(dues) + len(context_reconnect) + (1 if pending_passwords else 0),
        'audit_status': audit_cooldown_status(group),
        'chart': {
            'daily': summary['daily'], 'prev_daily': summary['prev_daily'],
            'upto': summary['pace']['day'] if summary['pace'] else len(summary['daily']),
            'label': summary['start'].strftime('%b'), 'prev_label': summary['prev_label'][:3],
        },
        'trend_chart': {
            'labels': [t['label'] for t in trend['months']],
            'values': [float(t['total']) for t in trend['months']],
            'params': [t['param'] for t in trend['months']],
            'selected': next(i for i, t in enumerate(trend['months']) if t['selected']),
            'partial': [t['partial'] for t in trend['months']],
            'avg': float(trend['avg']),
        },
    }
    return render(request, 'expenses/home.html', context)


@_require_expenses
def expenses_year(request):
    group = _group(request)
    current = fy_start_year(timezone.localdate())
    fy_start = parse_fy_param(request.GET.get('fy'), current)
    summary = fy_summary(group, fy_start)
    return render(request, 'expenses/year.html', {
        'summary': summary,
        'fy_start': fy_start,
        'fy_options': available_fys(group),
        'chart': {
            'labels': [m['label'] for m in summary['months']],
            'params': [m['param'] for m in summary['months']],
            'stack': summary['stack'],
            'avg': float(summary['avg_month']),
        },
    })


# ---------------------------------------------------------------------------
# Expense CRUD
# ---------------------------------------------------------------------------

def _save_expense(request, form, previous_category=None, creating=False):
    remember = form.cleaned_data.get('remember')
    obj = form.save(commit=False)
    obj.group = _group(request)
    if creating:
        obj.source = 'MANUAL'
        obj.created_by = request.user
        obj.member = obj.member or request.user
    if 'merchant' in form.changed_data or creating:
        manual_merchant(obj)
    if 'is_emi' in form.changed_data:
        if obj.is_emi and not obj.emi_component:
            obj.emi_component = 'PURCHASE'
        elif not obj.is_emi:
            obj.emi_component = ''
    new_category = obj.category
    obj.save()
    if new_category and (creating or new_category.pk != previous_category):
        learned = learn_category(obj, new_category, request.user, apply_to_similar=remember)
        if learned:
            messages.info(request, f'Learned: {obj.merchant} → {new_category.name} (re-filed {learned} past '
                                   f'transaction{"s" if learned != 1 else ""}).')
    elif not new_category and not creating and previous_category:
        obj.category_source = 'USER'
        obj.save(update_fields=['category_source'])
    apply_flags(obj)
    return obj


@_require_expenses
@require_POST
def expense_add(request):
    group = _group(request)
    form = ExpenseForm(request.POST, group=group)
    if form.is_valid():
        obj = _save_expense(request, form, creating=True)
        messages.success(request, f'Added ₹{obj.amount:,.0f} at {obj.merchant}.')
    else:
        messages.error(request, 'Could not add expense — ' + _form_errors(form))
    return safe_redirect(request, 'expenses_home')


@_require_expenses
@require_POST
def expense_edit(request, pk):
    group = _group(request)
    expense = get_object_or_404(_expenses(request), pk=pk, is_deleted=False)
    previous_category = expense.category_id  # is_valid() copies the POSTed values onto the instance
    form = ExpenseForm(request.POST, instance=expense, group=group)
    if form.is_valid():
        obj = _save_expense(request, form, previous_category)
        messages.success(request, f'Updated {obj.merchant}.')
    else:
        messages.error(request, 'Could not update expense — ' + _form_errors(form))
    return safe_redirect(request, 'expenses_home')


@_require_expenses
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(_expenses(request), pk=pk, is_deleted=False)
    if expense.source == 'MANUAL':
        expense.delete()
    else:
        expense.is_deleted = True
        expense.save(update_fields=['is_deleted', 'updated_at'])
    messages.success(request, f'Removed {expense.merchant}.')
    return safe_redirect(request, 'expenses_home')


@_require_expenses
@require_POST
def expense_review(request, pk):
    expense = get_object_or_404(_expenses(request), pk=pk)
    expense.flag_reviewed = request.POST.get('action') != 'reopen'
    expense.save(update_fields=['flag_reviewed', 'updated_at'])
    messages.success(request, 'Marked as fine.' if expense.flag_reviewed else 'Flag reopened.')
    return safe_redirect(request, 'expenses_home')


@_require_expenses
@require_POST
def expenses_ai_audit(request):
    """Run an on-demand Gemini AI forensic audit across recent transactions with rate-limiting guardrails."""
    group = _group(request)
    status = audit_cooldown_status(group)
    if not status['can_audit']:
        rem_msg = f"{status['remaining_days']}d {status['remaining_hours']}h" if status['remaining_days'] else f"{status['remaining_hours']}h"
        messages.warning(
            request,
            f"AI audit can only be run once a week. "
            f"Next audit is available in {rem_msg} (on {status['next_available']:%d %b at %I:%M %p})."
        )
        return safe_redirect(request, 'expenses_home')

    flagged_count = ai_audit_expenses(group, limit=60, user=request.user)
    if flagged_count > 0:
        messages.warning(
            request,
            f'AI forensic audit completed: flagged {flagged_count} suspicious transaction{"s" if flagged_count != 1 else ""} for review.'
        )
        return redirect(reverse('expenses_home') + '?flagged=1')
    messages.success(request, 'AI forensic audit completed: all recent transactions look healthy with no anomalies detected.')
    return safe_redirect(request, 'expenses_home')


# ---------------------------------------------------------------------------
# Settings: Gmail, cards, categories, learned rules
# ---------------------------------------------------------------------------

@_require_expenses
def expenses_settings(request):
    group = _group(request)
    ensure_default_categories(group)
    categories = ExpenseCategory.objects.filter(group=group).annotate(n=Count('expenses', filter=Q(expenses__is_deleted=False)))
    rules = MerchantRule.objects.filter(group=group).select_related('category').order_by('source', 'merchant_label')
    if _hides_investments(request):
        categories = categories.exclude(name=INVESTMENT_CATEGORY)
        rules = rules.exclude(category__name=INVESTMENT_CATEGORY)
    return render(request, 'expenses/settings.html', {
        'accounts': GmailAccount.objects.filter(group=group).select_related('user'),
        'gmail_configured': gmail.is_configured(),
        'sources': PaymentSource.objects.filter(group=group).select_related('owner')
                   .annotate(n=Count('expenses', filter=Q(expenses__is_deleted=False))),
        'categories': categories,
        'rules': rules,
        'members': group.members.filter(user_type__in=('PRIMARY', 'ACCOUNT_HOLDER')),
        'kind_choices': PaymentSource.KIND_CHOICES,
        'category_kinds': ExpenseCategory.KIND_CHOICES,
        'redirect_uri': _redirect_uri(request),
    })


def _redirect_uri(request):
    path = reverse('expenses_gmail_callback')
    return app_url(path) or request.build_absolute_uri(path)


@_require_expenses
def gmail_connect(request):
    try:
        state = secrets.token_urlsafe(24)
        request.session[_OAUTH_STATE_KEY] = state
        url = gmail.build_auth_url(_redirect_uri(request), state, login_hint=request.GET.get('hint', ''))
    except gmail.GmailError as exc:
        messages.error(request, str(exc))
        return redirect('expenses_settings')
    return redirect(url)


@_require_expenses
def gmail_callback(request):
    expected = request.session.pop(_OAUTH_STATE_KEY, None)
    if not expected or not secrets.compare_digest(expected, request.GET.get('state', '')):
        messages.error(request, 'Gmail connection expired or was tampered with — please try again.')
        return redirect('expenses_settings')
    if request.GET.get('error'):
        messages.error(request, 'Gmail access was not granted.')
        return redirect('expenses_settings')
    group = _group(request)
    try:
        tokens = gmail.exchange_code(request.GET.get('code', ''), _redirect_uri(request))
        client = gmail.GmailClient(tokens['refresh_token'])
        email = client.profile()['emailAddress'].lower()
    except (gmail.GmailError, gmail.GmailAuthError, KeyError) as exc:
        messages.error(request, f'Could not connect Gmail: {exc}')
        return redirect('expenses_settings')

    account, created = GmailAccount.objects.get_or_create(group=group, email=email, defaults={'user': request.user})
    if not created and account.user_id != request.user.pk and not request.user.is_primary:
        messages.error(request, f'{email} is already connected by another household member.')
        return redirect('expenses_settings')
    account.refresh_token = tokens['refresh_token']
    account.is_active = True
    account.last_error = ''
    account.save()

    result = sync_account(account, time_budget=INLINE_SYNC_SECONDS)
    tail = '' if result.complete else ' The rest of your history will import in the background.'
    messages.success(request, f'Connected {email}. Imported {result.transactions} transaction'
                              f'{"s" if result.transactions != 1 else ""} and {result.statements} statement'
                              f'{"s" if result.statements != 1 else ""}.{tail}')
    return redirect('expenses_home')


@_require_expenses
@require_POST
def gmail_sync(request, pk):
    account = get_object_or_404(GmailAccount, pk=pk, group=_group(request))
    if account.needs_reconnect:
        messages.error(request, f'{account.email} needs to be reconnected first.')
        return safe_redirect(request, 'expenses_settings')
    result = sync_account(account, time_budget=INLINE_SYNC_SECONDS)
    if result.error:
        messages.error(request, f'Sync failed for {account.email}: {result.error}')
    else:
        tail = '' if result.complete else ' More will import in the background.'
        messages.success(request, f'Synced {account.email}: {result.transactions} new transaction'
                                  f'{"s" if result.transactions != 1 else ""}.{tail}')
    return safe_redirect(request, 'expenses_settings')


@_require_expenses
@require_POST
def gmail_disconnect(request, pk):
    account = get_object_or_404(GmailAccount, pk=pk, group=_group(request))
    if account.user_id != request.user.pk and not request.user.is_primary:
        return HttpResponseForbidden('Only the person who connected this mailbox can disconnect it.')
    gmail.revoke(account.refresh_token)
    email = account.email
    account.delete()
    messages.success(request, f'Disconnected {email}. Imported transactions were kept.')
    return redirect('expenses_settings')


@_require_expenses
@require_POST
def category_save(request, pk=None):
    group = _group(request)
    instance = get_object_or_404(ExpenseCategory, pk=pk, group=group) if pk else ExpenseCategory(group=group)
    form = CategoryForm(request.POST, instance=instance, group=group)
    if form.is_valid():
        form.save()
        messages.success(request, f'Saved category {form.instance.name}.')
    else:
        messages.error(request, 'Could not save category — ' + _form_errors(form))
    return redirect(reverse('expenses_settings') + '#categories')


@_require_expenses
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk, group=_group(request))
    category.expenses.update(category=None, category_source='NONE')
    name = category.name
    category.delete()
    messages.success(request, f'Deleted {name}. Its transactions are now uncategorised.')
    return redirect(reverse('expenses_settings') + '#categories')


@_require_expenses
@require_POST
def source_save(request, pk=None):
    group = _group(request)
    instance = get_object_or_404(PaymentSource, pk=pk, group=group) if pk else PaymentSource(group=group, is_auto=False)
    form = PaymentSourceForm(request.POST, instance=instance, group=group)
    if form.is_valid():
        form.save()
        messages.success(request, f'Saved {form.instance.display_name}.')
    else:
        messages.error(request, 'Could not save — ' + _form_errors(form))
    return redirect(reverse('expenses_settings') + '#cards')


@_require_expenses
@require_POST
def rule_delete(request, pk):
    rules = MerchantRule.objects.filter(group=_group(request))
    if _hides_investments(request):
        rules = rules.exclude(category__name=INVESTMENT_CATEGORY)
    rule = get_object_or_404(rules, pk=pk)
    rule.delete()
    messages.success(request, f'Forgot the rule for {rule.merchant_label or rule.merchant_key}.')
    return redirect(reverse('expenses_settings') + '#rules')


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@_require_expenses
def statements_list(request):
    group = _group(request)
    return render(request, 'expenses/statements.html', {
        'statements': CardStatement.objects.filter(group=group).select_related('payment_source'),
        'cards': PaymentSource.objects.filter(group=group, kind='CREDIT_CARD'),
        'upload_form': StatementUploadForm(group=group),
        'today': timezone.localdate(),
    })


@_require_expenses
def statement_detail(request, pk):
    from decimal import Decimal
    group = _group(request)
    statement = get_object_or_404(CardStatement.objects.select_related('payment_source', 'duplicate_of'), pk=pk, group=group)
    lines = list(statement.lines.select_related(
        'matched_expense', 'matched_expense__category',
        'suggested_expense', 'suggested_expense__category',
    ))
    debits = [l for l in lines if not l.is_credit]
    payments = [l for l in lines if l.is_credit and l.match_method == 'SKIP']
    refunds = [l for l in lines if l.is_credit and l.match_method != 'SKIP']
    total_debits = sum((l.amount for l in debits), Decimal('0.00'))
    total_payments = sum((l.amount for l in payments), Decimal('0.00'))
    total_refunds = sum((l.amount for l in refunds), Decimal('0.00'))
    net_new_spends = total_debits - total_refunds
    math = {
        'total_debits': total_debits,
        'debit_count': len(debits),
        'total_payments': total_payments,
        'payment_count': len(payments),
        'total_refunds': total_refunds,
        'refund_count': len(refunds),
        'net_new_spends': net_new_spends,
    }
    return render(request, 'expenses/statement_detail.html', {
        'statement': statement,
        'lines': lines,
        'math': math,
        'today': timezone.localdate(),
    })


@_require_expenses
@require_POST
def statement_upload(request):
    group = _group(request)
    form = StatementUploadForm(request.POST, request.FILES, group=group)
    if not form.is_valid():
        messages.error(request, 'Could not upload statement — ' + _form_errors(form))
        return redirect('expenses_statements')
    card = form.cleaned_data['payment_source']
    password = form.cleaned_data.get('password', '')
    if password and form.cleaned_data.get('save_password'):
        card.statement_password = password
        card.save(update_fields=['statement_password_enc'])
    statement = CardStatement.objects.create(group=group, payment_source=card)
    read_pdf(statement, form.cleaned_data['pdf'].read(), password)
    _statement_message(request, statement)
    target_pk = statement.duplicate_of_id if (statement.status == 'DUPLICATE' and statement.duplicate_of_id) else statement.pk
    return redirect('expenses_statement_detail', pk=target_pk)


@_require_expenses
@require_POST
def statement_unlock(request, pk):
    statement = get_object_or_404(CardStatement, pk=pk, group=_group(request), status='NEEDS_PASSWORD')
    password = request.POST.get('password', '')
    if request.POST.get('save_password') and password:
        statement.payment_source.statement_password = password
        statement.payment_source.save(update_fields=['statement_password_enc'])
    read_pdf(statement, crypto.decrypt_bytes(statement.pdf_blob), password)
    _statement_message(request, statement)
    target_pk = statement.duplicate_of_id if (statement.status == 'DUPLICATE' and statement.duplicate_of_id) else statement.pk
    return redirect('expenses_statement_detail', pk=target_pk)


def _statement_message(request, statement):
    if statement.status == 'NEEDS_PASSWORD':
        messages.error(request, 'That password did not open the PDF.')
    elif statement.status == 'FAILED':
        messages.error(request, 'Could not read transactions from this PDF. Totals were saved if found.')
    elif statement.status == 'DUPLICATE':
        orig_date = f" from {statement.duplicate_of.statement_date}" if statement.duplicate_of and statement.duplicate_of.statement_date else ""
        messages.info(request, f'This statement was already imported{orig_date}. Showing existing record.')
    else:
        msg = (
            f'Read {statement.line_count} lines: {statement.matched_count} matched email alerts, '
            f'{statement.added_count} were missing and have been added.'
        )
        if statement.review_count:
            msg += f' {statement.review_count} lines need your confirmation.'
        messages.success(request, msg)


@_require_expenses
@require_POST
def statement_paid(request, pk):
    statement = get_object_or_404(CardStatement, pk=pk, group=_group(request))
    target = statement.duplicate_of if (statement.status == 'DUPLICATE' and statement.duplicate_of) else statement
    target.is_paid = not target.is_paid
    target.paid_at = timezone.localdate() if target.is_paid else None
    target.save(update_fields=['is_paid', 'paid_at'])
    if target.pk != statement.pk:
        statement.is_paid = target.is_paid
        statement.paid_at = target.paid_at
        statement.save(update_fields=['is_paid', 'paid_at'])
    messages.success(request, 'Marked as paid.' if target.is_paid else 'Marked as unpaid.')
    return safe_redirect(request, 'expenses_statements')


@_require_expenses
@require_POST
def statement_reconcile(request, pk):
    statement = get_object_or_404(CardStatement, pk=pk, group=_group(request))
    target = statement.duplicate_of if (statement.status == 'DUPLICATE' and statement.duplicate_of) else statement
    if target.status != 'PARSED':
        messages.error(request, 'Only parsed statements can be reconciled.')
        return redirect('expenses_statement_detail', pk=target.pk)
    matched, added = reconcile(target)
    msg = f'Re-checked: {matched} matched, {added} newly added.'
    if target.review_count:
        msg += f' {target.review_count} lines need your confirmation.'
    messages.success(request, msg)
    return redirect('expenses_statement_detail', pk=target.pk)


@_require_expenses
@require_POST
def statement_line_resolve(request, pk):
    group = _group(request)
    line = get_object_or_404(StatementLine.objects.select_related('statement'), pk=pk, statement__group=group)
    action = request.POST.get('action', '').strip().lower()
    if action not in ('link', 'add'):
        messages.error(request, 'Invalid action.')
        return redirect('expenses_statement_detail', pk=line.statement_id)

    ok = resolve_line(line, action)
    if ok:
        if action == 'link':
            messages.success(request, f'Linked "{line.description}" to existing expense.')
        else:
            messages.success(request, f'Added "{line.description}" as a new expense.')
    else:
        messages.error(request, 'Could not resolve line: target expense may have been deleted or matched elsewhere.')
    return redirect('expenses_statement_detail', pk=line.statement_id)
