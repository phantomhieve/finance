import calendar
import datetime
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Sum, Value, DecimalField, When
from django.db.models.functions import ExtractYear, ExtractMonth
from django.contrib import messages
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pftracker.utils import feature_enabled, safe_redirect

from .models import Transaction, HRAExpense, FinancialGoal, GoalIncrement, MonthlyGoalAdjustment, Note, MonthlySavingsComment
from .forms import (
    TransactionForm,
    GoalIncrementForm,
    FinancialGoalForm,
    MonthlyGoalAdjustmentForm,
    HRAExpenseForm,
    NoteForm,
    MonthlySavingsCommentForm,
)
from .services import (
    MONTH_ORDER,
    MONTH_TO_NUM,
    fy_date_range,
    get_month_date,
    resolve_per_month_goals,
    current_fy_start_year,
    parse_fy_param,
    fy_label,
    get_base_monthly_goal,
    get_fy_increments,
    get_fy_adjustments,
    apply_carry_forward,
    apply_monthly_adjustments,
    hra_spent as get_hra_spent,
    aggregate_transactions,
    group_user_filter,
)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _require_role(*allowed_types):
    """Decorator that restricts a view to specific user_type values."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.user_type not in allowed_types:
                return HttpResponseForbidden('You do not have permission to perform this action.')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def _safe_redirect(request, fallback='dashboard'):
    return safe_redirect(request, fallback)


def _require_feature(feature_name):
    """Decorator to gate a view behind a HouseholdConfig feature toggle."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not feature_enabled(request.user, feature_name):
                raise Http404
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _fy_context(request):
    """Parse FY from query params and return common FY context values."""
    today = timezone.now().date()
    current_fy = current_fy_start_year(today)
    fy_start = parse_fy_param(request.GET.get('fy'), current_fy)
    fy_start_date, fy_end_date = fy_date_range(fy_start)

    # Build FY options only for years where this group actually has data,
    # plus one extra future FY for planning.
    gf = group_user_filter(request.user)
    fy_years = set()

    for model, field in (
        (Transaction, "date"),
        (HRAExpense, "date"),
        (FinancialGoal, "month"),
    ):
        dates = (
            model.objects.filter(gf)
            .exclude(**{field: None})
            .annotate(_y=ExtractYear(field), _m=ExtractMonth(field))
            .values_list('_y', '_m')
            .distinct()
        )
        for y, m in dates:
            fy_years.add(y if m >= 4 else y - 1)

    # Ensure the current financial year is always included as a base option.
    fy_years.add(current_fy)

    min_fy = min(fy_years)
    max_fy = max(fy_years)
    # Fill in any gaps continuously, and add one future year for planning
    for y in range(min_fy, max_fy + 2):
        fy_years.add(y)

    return {
        'today': today,
        'current_fy': current_fy,
        'fy_start': fy_start,
        'fy_start_date': fy_start_date,
        'fy_end_date': fy_end_date,
        'fy_label': fy_label(fy_start),
        'fy_options': sorted(fy_years),
    }


# ---------------------------------------------------------------------------
# Dashboard (PRIMARY + ACCOUNT_HOLDER)
# ---------------------------------------------------------------------------

@login_required
@_require_feature('savings')
def dashboard(request):
    if not request.user.can_view_savings:
        return redirect('hra_tracker')

    fc = _fy_context(request)
    today, fy_start = fc['today'], fc['fy_start']
    gf = group_user_filter(request.user)

    transactions = Transaction.objects.filter(
        gf,
        date__gte=fc['fy_start_date'],
        date__lte=fc['fy_end_date'],
    )

    fy_goal_obj = FinancialGoal.objects.filter(gf, month=fc['fy_start_date']).first()
    if fy_goal_obj:
        base_monthly = float(fy_goal_obj.monthly_goal)
    else:
        base_monthly = apply_carry_forward(request.user, fc['fy_start_date'], get_base_monthly_goal(request.user))

    increments = get_fy_increments(request.user, fc['fy_start_date'], fc['fy_end_date'])
    adjustments = get_fy_adjustments(request.user, fc['fy_start_date'], fc['fy_end_date'])
    per_month_goals = resolve_per_month_goals(base_monthly, increments, fy_start)
    per_month_goals = apply_monthly_adjustments(per_month_goals, adjustments, fy_start)
    # Ensure the annual goal reflects base monthly goal plus all increments.
    total_goal = sum(per_month_goals.values())

    total_savings, total_transfers, total_income, total_expense = aggregate_transactions(transactions)
    hra_spent = get_hra_spent(request.user, fc['fy_start_date'], fc['fy_end_date'])

    goal_achieved = total_savings + total_income + (total_transfers - hra_spent)
    goal_remaining = total_goal - goal_achieved
    goal_pct = max(0, min(100, int((goal_achieved / total_goal) * 100))) if total_goal else 0

    monthly_data = _build_monthly_data(
        transactions, request.user, fy_start, today, per_month_goals
    )
    pace = _savings_pace(monthly_data, goal_achieved, total_goal, today, fc['fy_start_date'], fc['fy_end_date'])

    fy_transactions = transactions.order_by('-date', '-id')

    txn_form = TransactionForm(initial={'date': today})
    goal_form = GoalIncrementForm()
    adjust_form = MonthlyGoalAdjustmentForm()
    comment_form = MonthlySavingsCommentForm()
    fy_goal_form = FinancialGoalForm(initial={
        'fy_year': fy_start,
        'monthly_goal': base_monthly,
    })

    dashboard_chart_data = {
        'months': [m['short'] for m in monthly_data],
        'totals': [m['total'] for m in monthly_data],
        'goals': [m['goal'] for m in monthly_data],
        # None stops the "saved" line at the current month instead of running flat to March
        'cumulative': [m['cumulative'] if m['started'] else None for m in monthly_data],
        'cumulative_goals': [m['cumulative_goal'] for m in monthly_data],
    }

    context = {
        **fc,
        'total_savings': total_savings,
        'total_transfers': total_transfers,
        'total_income': total_income,
        'total_expense': total_expense,
        'total_goal': total_goal,
        'monthly_goal': base_monthly,
        'goal_achieved': goal_achieved,
        'goal_remaining': goal_remaining,
        'goal_surplus': max(0.0, -goal_remaining),
        'goal_pct': goal_pct,
        'pace': pace,
        'hra_balance': total_transfers - hra_spent,
        'monthly_data': monthly_data,
        'transactions': fy_transactions,
        'txn_form': txn_form,
        'goal_form': goal_form,
        'adjust_form': adjust_form,
        'comment_form': comment_form,
        'fy_goal_form': fy_goal_form,
        'increments': increments,
        'adjustments': adjustments,
        'dashboard_chart_data': dashboard_chart_data,
    }
    return render(request, 'tracker/dashboard.html', context)


def _savings_pace(monthly_data, achieved, total_goal, today, fy_start_date, fy_end_date):
    """Where the FY stands against a steady month-by-month climb to the annual goal.

    Open FY: gap vs the goal expected by today (current month pro-rated) and the monthly
    amount still needed. Closed FY: final verdict. Future FY: None.
    """
    if today < fy_start_date:
        return None
    if today > fy_end_date:
        gap = achieved - total_goal
        return {'state': 'closed', 'hit': gap >= 0, 'gap': gap, 'gap_abs': abs(gap)}
    idx = (today.month - 4) % 12
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    expected = sum(m['goal'] for m in monthly_data[:idx]) + monthly_data[idx]['goal'] * today.day / days_in_month
    months_left = 12 - idx
    still_needed = max(0.0, total_goal - achieved)
    return {
        'state': 'open',
        'gap': achieved - expected,
        'gap_abs': abs(achieved - expected),
        'months_left': months_left,
        'need_per_month': still_needed / months_left,
    }


def _build_monthly_data(transactions, user, fy_start, today, per_month_goals):
    """Build the per-month breakdown list used by the dashboard template."""
    # Single query: aggregate all months and types at once
    monthly_agg = (
        transactions
        .annotate(_y=ExtractYear('date'), _m=ExtractMonth('date'))
        .values('_y', '_m')
        .annotate(
            savings=Sum(Case(When(type='SAVINGS', then='amount'), default=Value(0), output_field=DecimalField())),
            income=Sum(Case(When(type='EXTRA_INCOME', then='amount'), default=Value(0), output_field=DecimalField())),
            expense=Sum(Case(When(type='EXPENSE', then='amount'), default=Value(0), output_field=DecimalField())),
        )
    )
    agg_map = {(r['_y'], r['_m']): r for r in monthly_agg}

    fy_start_date, fy_end_date = fy_date_range(fy_start)
    comments_qs = MonthlySavingsComment.objects.filter(
        group_user_filter(user), month__gte=fy_start_date, month__lte=fy_end_date,
    )
    comments_map = {(c.month.year, c.month.month): c for c in comments_qs}

    monthly_data = []
    cumulative = 0.0
    cumulative_goal = 0.0

    for month_name in MONTH_ORDER:
        m_num = MONTH_TO_NUM[month_name]
        m_year = fy_start if m_num >= 4 else fy_start + 1
        m_date = datetime.date(m_year, m_num, 1)
        started = m_date <= today

        row = agg_map.get((m_year, m_num), {})
        savings = float(row.get('savings') or 0)
        income = float(row.get('income') or 0)
        expense = float(row.get('expense') or 0)

        total_put = savings + income - expense
        cumulative += total_put

        monthly_goal = per_month_goals[month_name]
        cumulative_goal += (monthly_goal or 0)
        pct = min(100, int(total_put / monthly_goal * 100)) if monthly_goal and started and total_put > 0 else 0

        if total_put >= monthly_goal and started and total_put > 0:
            status = 'good'
        elif total_put > 0 and started:
            status = 'partial'
        elif started:
            status = 'missed'
        else:
            status = 'future'

        comment_obj = comments_map.get((m_year, m_num))

        monthly_data.append({
            'name': month_name,
            'short': month_name[:3],
            'total': total_put,
            'cumulative': cumulative,
            'cumulative_goal': cumulative_goal,
            'goal': monthly_goal,
            'surplus': total_put - monthly_goal,
            'status': status,
            'started': started,
            'pct': pct,
            'comment': comment_obj.comment if comment_obj else '',
            'month_date': m_date.isoformat(),
        })

    return monthly_data


# ---------------------------------------------------------------------------
# Transaction / HRA CRUD factory (PRIMARY + ACCOUNT_HOLDER only)
# ---------------------------------------------------------------------------

def _make_tracker_crud(model_class, form_class, label, redirect_to='dashboard',
                       allowed_roles=('PRIMARY', 'ACCOUNT_HOLDER')):
    """Generate add / edit / delete views for user-owned tracker models."""

    @login_required
    @require_POST
    @_require_role(*allowed_roles)
    def add_view(request):
        form = form_class(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, f'₹{obj.amount:,.0f} {label} entry saved.')
        else:
            messages.error(request, 'Could not save entry. Please check the form fields.')
        return _safe_redirect(request, redirect_to)

    @login_required
    @require_POST
    @_require_role(*allowed_roles)
    def edit_view(request, pk):
        gf = group_user_filter(request.user)
        obj = get_object_or_404(model_class, pk=pk, **_gf_kwargs(gf))
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'₹{obj.amount:,.0f} {label} entry updated.')
        else:
            messages.error(request, 'Could not update entry. Please check the form fields.')
        return _safe_redirect(request, redirect_to)

    @login_required
    @require_POST
    @_require_role(*allowed_roles)
    def delete_view(request, pk):
        gf = group_user_filter(request.user)
        obj = get_object_or_404(model_class, pk=pk, **_gf_kwargs(gf))
        amt = obj.amount
        obj.delete()
        messages.success(request, f'{label} entry deleted: ₹{amt:,.0f}')
        return _safe_redirect(request, redirect_to)

    add_view.__name__ = f'add_{model_class.__name__.lower()}'
    edit_view.__name__ = f'edit_{model_class.__name__.lower()}'
    delete_view.__name__ = f'delete_{model_class.__name__.lower()}'

    return add_view, edit_view, delete_view


# Savings entries are editable by the PRIMARY holder only; the spouse has
# read-only access to Monthly Savings.
add_transaction, edit_transaction, delete_transaction = _make_tracker_crud(
    Transaction, TransactionForm, 'Transaction', 'dashboard',
    allowed_roles=('PRIMARY',))

add_hra_entry, edit_hra_entry, delete_hra_entry = _make_tracker_crud(
    HRAExpense, HRAExpenseForm, 'HRA', 'hra_tracker')


# ---------------------------------------------------------------------------
# Goal management (PRIMARY only — spouse has read-only Monthly Savings)
# ---------------------------------------------------------------------------

@login_required
@require_POST
@_require_role('PRIMARY')
def add_goal_increment(request):
    gf = group_user_filter(request.user)
    inc_id = request.POST.get('increment_id')
    if inc_id:
        instance = GoalIncrement.objects.filter(gf, id=inc_id).first()
        form = GoalIncrementForm(request.POST, instance=instance)
        action_msg = 'updated'
    else:
        form = GoalIncrementForm(request.POST)
        action_msg = 'added'

    if form.is_valid():
        inc = form.save(commit=False)
        inc.user = request.user
        inc.save()
        messages.success(
            request,
            f'Increment of ₹{inc.increment_amount:,.0f} {action_msg} from {inc.effective_month.strftime("%b %Y")}.',
        )
    else:
        messages.error(request, 'Could not save goal update.')
    return _safe_redirect(request, 'dashboard')


@login_required
@require_POST
@_require_role('PRIMARY')
def delete_goal_increment(request, inc_id):
    gf = group_user_filter(request.user)
    deleted, _ = GoalIncrement.objects.filter(gf, id=inc_id).delete()
    if deleted:
        messages.success(request, 'Increment removed.')
    else:
        messages.error(request, 'Could not remove increment.')
    return _safe_redirect(request, 'dashboard')


@login_required
@require_POST
@_require_role('PRIMARY')
def set_annual_goal(request):
    """Create or update the FinancialGoal for a specific FY start year."""
    form = FinancialGoalForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Could not save FY goal. Check the values.')
        return _safe_redirect(request, 'dashboard')

    fy_year = form.cleaned_data['fy_year']
    month = datetime.date(fy_year, 4, 1)
    gf = group_user_filter(request.user)
    goal_obj = FinancialGoal.objects.filter(gf, month=month).first()
    if goal_obj:
        created = False
    else:
        goal_obj = FinancialGoal(user=request.user, month=month, total_goal=0, monthly_goal=0)
        goal_obj.save()
        created = True

    goal_form = FinancialGoalForm(request.POST, instance=goal_obj)
    if goal_form.is_valid():
        obj = goal_form.save(commit=False)
        obj.user = obj.user or request.user
        obj.month = month
        obj.total_goal = obj.monthly_goal * 12
        obj.save()
        action = 'created' if created else 'updated'
        messages.success(
            request,
            f'FY {fy_year}-{str(fy_year + 1)[-2:]} goal {action}: '
            f'₹{obj.total_goal:,.0f} annual / ₹{obj.monthly_goal:,.0f}/mo.',
        )
    else:
        messages.error(request, 'Could not save FY goal. Check the values.')
    return _safe_redirect(request, 'dashboard')


@login_required
@require_POST
@_require_role('PRIMARY')
def add_goal_adjustment(request):
    """Create or update a one-off monthly adjustment."""
    gf = group_user_filter(request.user)
    adj_id = request.POST.get('adjustment_id')
    if adj_id:
        instance = MonthlyGoalAdjustment.objects.filter(gf, id=adj_id).first()
        form = MonthlyGoalAdjustmentForm(request.POST, instance=instance)
        action_msg = 'updated'
    else:
        form = MonthlyGoalAdjustmentForm(request.POST)
        action_msg = 'added'

    if form.is_valid():
        adj = form.save(commit=False)
        adj.user = request.user
        adj.save()
        messages.success(
            request,
            f'One-off adjustment of ₹{adj.adjustment_amount:,.0f} {action_msg} for {adj.month.strftime("%b %Y")}.',
        )
    else:
        messages.error(request, 'Could not save monthly adjustment.')
    return _safe_redirect(request, 'dashboard')


@login_required
@require_POST
@_require_role('PRIMARY')
def delete_goal_adjustment(request, adj_id):
    gf = group_user_filter(request.user)
    deleted, _ = MonthlyGoalAdjustment.objects.filter(gf, id=adj_id).delete()
    if deleted:
        messages.success(request, 'Monthly adjustment removed.')
    else:
        messages.error(request, 'Could not remove adjustment.')
    return _safe_redirect(request, 'dashboard')


@login_required
@require_POST
@_require_role('PRIMARY')
def save_month_comment(request):
    """Create or update a comment for a specific month's savings."""
    month_str = request.POST.get('month', '')
    comment_text = request.POST.get('comment', '').strip()
    try:
        month_date = datetime.date.fromisoformat(month_str)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid month.')
        return _safe_redirect(request, 'dashboard')

    if comment_text:
        _, created = MonthlySavingsComment.objects.update_or_create(
            user=request.user,
            month=month_date,
            defaults={'comment': comment_text},
        )
        action = 'added' if created else 'updated'
        messages.success(request, f'Comment {action} for {month_date.strftime("%b %Y")}.')
    else:
        # Empty comment → delete if exists
        deleted, _ = MonthlySavingsComment.objects.filter(
            user=request.user, month=month_date,
        ).delete()
        if deleted:
            messages.success(request, f'Comment removed for {month_date.strftime("%b %Y")}.')
    return _safe_redirect(request, 'dashboard')


# ---------------------------------------------------------------------------
# HRA tracker (all roles — LANDLORD is view-only)
# ---------------------------------------------------------------------------

@login_required
@_require_feature('hra')
def hra_tracker(request):
    fc = _fy_context(request)
    gf = group_user_filter(request.user)

    expenses = HRAExpense.objects.filter(
        gf,
        date__gte=fc['fy_start_date'],
        date__lte=fc['fy_end_date'],
    ).order_by('-date')

    total_expense = float(
        expenses.filter(hra_type='EXPENSE').aggregate(t=Sum('amount'))['t'] or 0
    )
    total_additions = float(
        expenses.filter(hra_type__in=['RENT_PAID', 'REVERT']).aggregate(t=Sum('amount'))['t'] or 0
    )
    remaining_balance = total_additions - total_expense

    monthly_data = _build_hra_monthly(expenses, fc['fy_start'], fc['today'])

    mode_metrics = list(
        expenses.values('mode_of_payment')
        .annotate(total=Sum('amount'))
        .exclude(mode_of_payment='')
        .order_by('-total')[:6]
    )

    txn_form = HRAExpenseForm(initial={'date': fc['today']})

    context = {
        **fc,
        'expenses': expenses,
        'total_expense': total_expense,
        'total_revert': total_additions,
        'total_additions': total_additions,
        'remaining_balance': remaining_balance,
        'monthly_data': monthly_data,
        'mode_metrics': mode_metrics,
        'txn_form': txn_form,
    }
    return render(request, 'tracker/hra.html', context)


def _build_hra_monthly(expenses, fy_start, today):
    """Build per-month HRA breakdown for the month grid."""
    import calendar
    qs = expenses.order_by()
    monthly_agg = (
        qs
        .annotate(_y=ExtractYear('date'), _m=ExtractMonth('date'))
        .values('_y', '_m')
        .annotate(
            expense=Sum(Case(When(hra_type='EXPENSE', then='amount'), default=Value(0), output_field=DecimalField())),
            addition=Sum(Case(When(hra_type__in=['RENT_PAID', 'REVERT'], then='amount'), default=Value(0), output_field=DecimalField())),
            rent_paid=Sum(Case(When(hra_type='RENT_PAID', then='amount'), default=Value(0), output_field=DecimalField())),
        )
    )
    agg_map = {(r['_y'], r['_m']): r for r in monthly_agg}

    monthly_data = []
    for month_name in MONTH_ORDER:
        m_num = MONTH_TO_NUM[month_name]
        m_year = fy_start if m_num >= 4 else fy_start + 1
        m_date = get_month_date(month_name, fy_start)
        started = m_date <= today
        last_day = calendar.monthrange(m_year, m_num)[1]
        month_ended = datetime.date(m_year, m_num, last_day) < today

        row = agg_map.get((m_year, m_num), {})
        m_expense = float(row.get('expense') or 0)
        m_addition = float(row.get('addition') or 0)
        m_rent_paid = float(row.get('rent_paid') or 0)

        # Status logic:
        # - rent_paid: month ended & rent was paid → green
        # - rent_due:  month ended & rent NOT paid → red
        # - current:   month in progress (started but not ended)
        # - future:    month not started
        if not started:
            status = 'future'
        elif not month_ended:
            # Current month
            if m_rent_paid > 0:
                status = 'rent_paid'
            else:
                status = 'current'
        else:
            # Past month (ended)
            if m_rent_paid > 0:
                status = 'rent_paid'
            else:
                status = 'rent_due'

        monthly_data.append({
            'name': month_name,
            'short': month_name[:3],
            'expense': m_expense,
            'addition': m_addition,
            'rent_paid': m_rent_paid,
            'net': m_addition - m_expense,
            'started': started,
            'month_ended': month_ended,
            'status': status,
        })
    return monthly_data


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _gf_kwargs(gf):
    """Convert a Q object group filter into kwargs usable with get_object_or_404.
    Extracts the underlying lookup from the Q for simple single-condition filters."""
    for child in gf.children:
        if isinstance(child, tuple):
            return {child[0]: child[1]}
    return {}



# ---------------------------------------------------------------------------
# Notes (all authenticated users, own notes only)
# ---------------------------------------------------------------------------

@login_required
@_require_feature('notes')
def notes_list(request):
    """Display all notes for the current user, with section and FY filter."""
    fc = _fy_context(request)
    today = fc['today']
    current_fy = fc['current_fy']

    section_filter = request.GET.get('section', '')
    fy_filter = request.GET.get('fy', '')

    notes_qs = Note.objects.filter(user=request.user)
    if section_filter:
        notes_qs = notes_qs.filter(section=section_filter)

    # Filter by financial year. If 'fy' is not provided, default to current FY.
    active_fy = None
    if fy_filter == 'all':
        pass
    elif fy_filter:
        try:
            active_fy = int(fy_filter)
            notes_qs = notes_qs.filter(financial_year=active_fy)
        except ValueError:
            pass
    else:
        active_fy = current_fy
        notes_qs = notes_qs.filter(financial_year=active_fy)

    # All unique sections this user has used (for the filter pills + datalist)
    all_sections = (
        Note.objects.filter(user=request.user)
        .exclude(section='')
        .values_list('section', flat=True)
        .distinct()
        .order_by('section')
    )

    # Re-use the exact same FY options from dashboard context
    fy_options = [{'year': y, 'label': f"{y}-{y+1}"} for y in fc['fy_options']]

    note_form = NoteForm(initial={'date': today, 'financial_year': current_fy})

    # Separate Todo items from regular notes
    todo_open = []
    todo_done = []
    regular_notes = []
    for note in notes_qs:
        if note.section == 'Pending' and note.initial_amount and note.pending_amount:
            try:
                initial = float(note.initial_amount)
                pending = float(note.pending_amount)
                if initial > 0:
                    note.settled_pct = max(0, min(100, int((initial - pending) / initial * 100)))
                else:
                    note.settled_pct = 0
            except (ValueError, TypeError, ZeroDivisionError):
                note.settled_pct = 0
        else:
            note.settled_pct = None

        if note.section == 'Todo':
            if note.is_done:
                todo_done.append(note)
            else:
                todo_open.append(note)
        else:
            regular_notes.append(note)

    context = {
        'notes': regular_notes,
        'todo_open': todo_open,
        'todo_done': todo_done,
        'note_form': note_form,
        'all_sections': list(all_sections),
        'active_section': section_filter,
        'fy_options': fy_options,
        'active_fy': active_fy,
        'today': today,
        'current_fy': current_fy,
    }
    return render(request, 'tracker/notes.html', context)


@login_required
@require_POST
def add_note(request):
    form = NoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.user = request.user
        note.save()
        messages.success(request, f'Note "{note.title}" saved.')
    else:
        messages.error(request, 'Could not save note. Please check the fields.')
    return safe_redirect(request, 'notes_list')


@login_required
@require_POST
def edit_note(request, pk):
    note = get_object_or_404(Note, pk=pk, user=request.user)
    form = NoteForm(request.POST, instance=note)
    if form.is_valid():
        form.save()
        messages.success(request, f'Note "{note.title}" updated.')
    else:
        messages.error(request, 'Could not update note.')
    return safe_redirect(request, 'notes_list')


@login_required
@require_POST
def delete_note(request, pk):
    note = get_object_or_404(Note, pk=pk, user=request.user)
    title = note.title
    note.delete()
    messages.success(request, f'Note "{title}" deleted.')
    return safe_redirect(request, 'notes_list')


@login_required
@require_POST
def toggle_todo(request, pk):
    """Toggle the is_done state of a Todo note."""
    note = get_object_or_404(Note, pk=pk, user=request.user, section='Todo')
    note.is_done = not note.is_done
    if note.is_done:
        from django.utils import timezone
        note.done_at = timezone.now()
    else:
        note.done_at = None
    note.save(update_fields=['is_done', 'done_at', 'updated_at'])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'is_done': note.is_done})

    action = 'completed' if note.is_done else 'reopened'
    messages.success(request, f'Todo "{note.title}" {action}.')
    return safe_redirect(request, 'notes_list')


# ---------------------------------------------------------------------------
# Auth views
# ---------------------------------------------------------------------------

def login_view(request):
    User = get_user_model()
    ctx = {}
    if settings.DEBUG:
        ctx['dev_users'] = User.objects.filter(is_active=True).order_by('username')
    return render(request, 'tracker/login.html', ctx)


def dev_login(request):
    """DEBUG-only: log in as any user without credentials."""
    if not settings.DEBUG:
        raise Http404
    User = get_user_model()
    uid = request.GET.get('uid') or request.POST.get('uid')
    if not uid:
        messages.error(request, 'No user selected.')
        return redirect('login')
    try:
        user = User.objects.get(pk=int(uid), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'User not found.')
        return redirect('login')
    login(request, user, backend='allauth.account.auth_backends.AuthenticationBackend')
    return redirect(settings.LOGIN_REDIRECT_URL)
