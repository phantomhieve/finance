import datetime
import logging
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

from pftracker.utils import safe_redirect

from .models import Transaction, HRAExpense, FinancialGoal, GoalIncrement, MonthlyGoalAdjustment
from .forms import (
    TransactionForm,
    GoalIncrementForm,
    FinancialGoalForm,
    MonthlyGoalAdjustmentForm,
    HRAExpenseForm,
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
    get_base_goal,
    get_fy_increments,
    get_fy_adjustments,
    apply_carry_forward,
    apply_monthly_adjustments,
    aggregate_hra,
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

    if not fy_years:
        fy_years.add(current_fy)

    max_fy = max(fy_years)
    fy_years.add(max_fy + 1)  # one extra FY on the right to plan ahead

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
        goal_obj = fy_goal_obj
        total_goal = float(goal_obj.total_goal)
        base_monthly = float(goal_obj.monthly_goal)
    else:
        goal_obj, total_goal, base_monthly = get_base_goal(request.user)
        base_monthly = apply_carry_forward(request.user, fc['fy_start_date'], base_monthly)

    increments = get_fy_increments(request.user, fc['fy_start_date'], fc['fy_end_date'])
    adjustments = get_fy_adjustments(request.user, fc['fy_start_date'], fc['fy_end_date'])
    per_month_goals = resolve_per_month_goals(base_monthly, increments, fy_start)
    per_month_goals = apply_monthly_adjustments(per_month_goals, adjustments, fy_start)
    # Ensure the annual goal reflects base monthly goal plus all increments.
    total_goal = sum(per_month_goals.values())

    total_savings, total_transfers, total_income = aggregate_transactions(transactions)
    hra_spent, hra_additions, hra_net = aggregate_hra(
        request.user, fc['fy_start_date'], fc['fy_end_date']
    )

    goal_achieved = total_savings + total_income + (total_transfers - hra_spent)
    goal_remaining = total_goal - goal_achieved
    goal_pct = min(100, int((goal_achieved / total_goal) * 100)) if total_goal else 0

    monthly_data = _build_monthly_data(
        transactions, request.user, fy_start, today, per_month_goals
    )

    recent_transactions = transactions.order_by('-date')[:50]

    txn_form = TransactionForm(initial={'date': today})
    goal_form = GoalIncrementForm()
    adjust_form = MonthlyGoalAdjustmentForm()
    fy_goal_form = FinancialGoalForm(initial={
        'fy_year': fy_start,
        'monthly_goal': base_monthly,
    })

    dashboard_chart_data = {
        'months': [m['short'] for m in monthly_data],
        'totals': [float(m['total']) if m.get('total') else 0 for m in monthly_data],
        'goals': [float(m['goal']) for m in monthly_data],
        'cumulative': [float(m['cumulative']) if m.get('cumulative') else 0 for m in monthly_data],
        'cumulative_goals': [float(m['cumulative_goal']) if m.get('cumulative_goal') else 0 for m in monthly_data],
    }

    context = {
        **fc,
        'current_fy_start': fc['current_fy'],
        'total_savings': total_savings,
        'total_transfers': total_transfers,
        'total_income': total_income,
        'total_goal': total_goal,
        'monthly_goal': base_monthly,
        'goal_achieved': goal_achieved,
        'goal_remaining': goal_remaining,
        'goal_pct': goal_pct,
        'hra_additions': hra_additions,
        'hra_spent': hra_spent,
        'hra_net': hra_net,
        'hra_balance': total_transfers - hra_spent,
        'monthly_data': monthly_data,
        'recent_transactions': recent_transactions,
        'txn_form': txn_form,
        'goal_form': goal_form,
        'adjust_form': adjust_form,
        'fy_goal_form': fy_goal_form,
        'increments': increments,
        'adjustments': adjustments,
        'goal_obj': goal_obj,
        'dashboard_chart_data': dashboard_chart_data,
    }
    return render(request, 'tracker/dashboard.html', context)


def _build_monthly_data(transactions, user, fy_start, today, per_month_goals):
    """Build the per-month breakdown list used by the dashboard template."""
    # Single query: aggregate all months and types at once
    monthly_agg = (
        transactions
        .annotate(_y=ExtractYear('date'), _m=ExtractMonth('date'))
        .values('_y', '_m')
        .annotate(
            savings=Sum(Case(When(type='SAVINGS', then='amount'), default=Value(0), output_field=DecimalField())),
            transfers=Sum(Case(When(type='TRANSFER', then='amount'), default=Value(0), output_field=DecimalField())),
            income=Sum(Case(When(type='EXTRA_INCOME', then='amount'), default=Value(0), output_field=DecimalField())),
        )
    )
    agg_map = {(r['_y'], r['_m']): r for r in monthly_agg}

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
        transfers = float(row.get('transfers') or 0)
        income = float(row.get('income') or 0)

        total_put = savings + income
        cumulative += total_put

        monthly_goal = per_month_goals[month_name]
        cumulative_goal += (monthly_goal or 0)
        pct = min(100, int(total_put / monthly_goal * 100)) if monthly_goal and started else 0

        if total_put >= monthly_goal and started and total_put > 0:
            status = 'good'
        elif total_put > 0 and started:
            status = 'partial'
        elif started:
            status = 'missed'
        else:
            status = 'future'

        monthly_data.append({
            'name': month_name,
            'short': month_name[:3],
            'savings': savings,
            'transfers': transfers,
            'income': income,
            'total': total_put,
            'cumulative': cumulative,
            'cumulative_goal': cumulative_goal,
            'goal': monthly_goal,
            'surplus': total_put - monthly_goal,
            'status': status,
            'started': started,
            'pct': pct,
        })

    return monthly_data


# ---------------------------------------------------------------------------
# Transaction / HRA CRUD factory (PRIMARY + ACCOUNT_HOLDER only)
# ---------------------------------------------------------------------------

def _make_tracker_crud(model_class, form_class, label, redirect_to='dashboard'):
    """Generate add / edit / delete views for user-owned tracker models."""

    @login_required
    @require_POST
    @_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
    @_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
    @_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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


add_transaction, edit_transaction, delete_transaction = _make_tracker_crud(
    Transaction, TransactionForm, 'Transaction', 'dashboard')

add_hra_entry, edit_hra_entry, delete_hra_entry = _make_tracker_crud(
    HRAExpense, HRAExpenseForm, 'HRA', 'hra_tracker')


# ---------------------------------------------------------------------------
# Goal management (PRIMARY + ACCOUNT_HOLDER only)
# ---------------------------------------------------------------------------

@login_required
@require_POST
@_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
@_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
@_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
@_require_role('PRIMARY', 'ACCOUNT_HOLDER')
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
@_require_role('PRIMARY', 'ACCOUNT_HOLDER')
def delete_goal_adjustment(request, adj_id):
    gf = group_user_filter(request.user)
    deleted, _ = MonthlyGoalAdjustment.objects.filter(gf, id=adj_id).delete()
    if deleted:
        messages.success(request, 'Monthly adjustment removed.')
    else:
        messages.error(request, 'Could not remove adjustment.')
    return _safe_redirect(request, 'dashboard')


# ---------------------------------------------------------------------------
# HRA tracker (all roles — LANDLORD is view-only)
# ---------------------------------------------------------------------------

@login_required
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
    # queryset must have no lingering ORDER BY: otherwise values().annotate()
    # can GROUP BY ordering columns too, yielding multiple buckets per calendar
    # month—the dict below then keeps only one row per (year, month) and hides
    # the rest of that month's totals.
    qs = expenses.order_by()
    monthly_agg = (
        qs
        .annotate(_y=ExtractYear('date'), _m=ExtractMonth('date'))
        .values('_y', '_m')
        .annotate(
            expense=Sum(Case(When(hra_type='EXPENSE', then='amount'), default=Value(0), output_field=DecimalField())),
            addition=Sum(Case(When(hra_type__in=['RENT_PAID', 'REVERT'], then='amount'), default=Value(0), output_field=DecimalField())),
        )
    )
    agg_map = {(r['_y'], r['_m']): r for r in monthly_agg}

    monthly_data = []
    for month_name in MONTH_ORDER:
        m_num = MONTH_TO_NUM[month_name]
        m_year = fy_start if m_num >= 4 else fy_start + 1
        started = get_month_date(month_name, fy_start) <= today

        row = agg_map.get((m_year, m_num), {})
        m_expense = float(row.get('expense') or 0)
        m_addition = float(row.get('addition') or 0)

        if m_addition > 0 and m_expense == 0:
            status = 'good'
        elif m_expense > 0:
            status = 'partial'
        elif started:
            status = 'missed'
        else:
            status = 'future'

        monthly_data.append({
            'name': month_name,
            'short': month_name[:3],
            'expense': m_expense,
            'addition': m_addition,
            'net': m_addition - m_expense,
            'started': started,
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
# Admin-only views (superuser)
# ---------------------------------------------------------------------------

def _require_superuser(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise Http404
        return view_func(request, *args, **kwargs)
    return _wrapped


@login_required
@_require_superuser
def admin_monitor(request):
    return render(request, 'tracker/admin_monitor.html')


logger = logging.getLogger(__name__)


@login_required
@_require_superuser
def server_metrics(request):
    """Scrape local Prometheus exporters and return a metrics snapshot."""
    import requests as http_requests
    import time as _time

    now = _time.time()

    def _scrape(url):
        try:
            r = http_requests.get(url, timeout=3)
            return r.text if r.ok else ''
        except Exception:
            return ''

    def _parse(text, name, labels=None):
        """Extract a single metric value from Prometheus text format."""
        for line in text.splitlines():
            if not line.startswith(name):
                continue
            if labels:
                if not all(f'{k}="{v}"' in line for k, v in labels.items()):
                    continue
            try:
                return float(line.split()[-1])
            except (ValueError, IndexError):
                continue
        return None

    def _parse_all(text, name, label_key=None):
        """Extract all series for a metric, keyed by a label value."""
        results = {}
        for line in text.splitlines():
            if not line.startswith(name + '{'):
                continue
            try:
                val = float(line.split()[-1])
                if label_key:
                    start = line.index(f'{label_key}="') + len(label_key) + 2
                    end = line.index('"', start)
                    key = line[start:end]
                else:
                    key = ''
                results[key] = val
            except (ValueError, IndexError):
                continue
        return results

    node_text = _scrape('http://localhost:9100/metrics')
    pg_text = _scrape('http://localhost:9187/metrics')

    # --- Node metrics ---
    boot_time = _parse(node_text, 'node_boot_time_seconds')
    mem_total = _parse(node_text, 'node_memory_MemTotal_bytes')
    mem_avail = _parse(node_text, 'node_memory_MemAvailable_bytes')
    disk_total = _parse(node_text, 'node_filesystem_size_bytes', {'mountpoint': '/', 'fstype': 'ext4'})
    disk_avail = _parse(node_text, 'node_filesystem_avail_bytes', {'mountpoint': '/', 'fstype': 'ext4'})
    net_rx = _parse(node_text, 'node_network_receive_bytes_total', {'device': 'enp4s0'})
    net_tx = _parse(node_text, 'node_network_transmit_bytes_total', {'device': 'enp4s0'})
    load1 = _parse(node_text, 'node_load1')
    load5 = _parse(node_text, 'node_load5')
    load15 = _parse(node_text, 'node_load15')

    cpu_modes = _parse_all(node_text, 'node_cpu_seconds_total', 'mode')
    cpu_count = 0
    for line in node_text.splitlines():
        if line.startswith('node_cpu_seconds_total{') and 'mode="idle"' in line:
            cpu_count += 1

    # --- Postgres metrics ---
    pg_up = _parse(pg_text, 'pg_up')
    pg_conns = _parse_all(pg_text, 'pg_stat_database_numbackends', 'datname')
    pg_sizes = _parse_all(pg_text, 'pg_database_size_bytes', 'datname')
    pg_hits = _parse_all(pg_text, 'pg_stat_database_blks_hit', 'datname')
    pg_reads = _parse_all(pg_text, 'pg_stat_database_blks_read', 'datname')

    user_dbs = {k: v for k, v in pg_conns.items()
                if k not in ('template0', 'template1')}
    total_conns = sum(user_dbs.values()) if user_dbs else 0
    total_size = sum(v for k, v in pg_sizes.items()
                     if k not in ('template0', 'template1'))
    total_hits = sum(v for k, v in pg_hits.items()
                     if k not in ('template0', 'template1'))
    total_reads = sum(v for k, v in pg_reads.items()
                      if k not in ('template0', 'template1'))
    cache_ratio = total_hits / (total_hits + total_reads) if (total_hits + total_reads) > 0 else None

    # --- Website check ---
    web_up = False
    web_ms = None
    health_url = getattr(settings, 'VAULT_HEALTH_CHECK_URL', '')
    if health_url:
        try:
            t0 = _time.time()
            req_kwargs = {'timeout': 5, 'allow_redirects': False}
            health_host = getattr(settings, 'VAULT_HEALTH_CHECK_HOST', '')
            if health_host:
                req_kwargs['headers'] = {'Host': health_host}
            wr = http_requests.get(health_url, **req_kwargs)
            web_ms = round((_time.time() - t0) * 1000, 1)
            web_up = wr.status_code in (200, 302)
        except Exception:
            pass

    return JsonResponse({
        'ts': now,
        'node': {
            'boot_time': boot_time,
            'uptime': round(now - boot_time) if boot_time else None,
            'cpu_modes': cpu_modes,
            'cpu_count': cpu_count,
            'mem_total': mem_total,
            'mem_available': mem_avail,
            'disk_total': disk_total,
            'disk_available': disk_avail,
            'net_rx': net_rx,
            'net_tx': net_tx,
            'load1': load1,
            'load5': load5,
            'load15': load15,
        },
        'pg': {
            'up': pg_up == 1,
            'connections': total_conns,
            'db_size': total_size,
            'cache_ratio': cache_ratio,
        },
        'web': {
            'up': web_up,
            'response_ms': web_ms,
        },
    })


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
