import datetime

from django.db.models import Case, Sum, Q, When, Value, DecimalField

from pftracker.utils import (  # noqa: F401 — re-exported for tracker.views
    fy_start_year as current_fy_start_year,
    fy_label,
)
from .models import (
    HRAExpense,
    FinancialGoal,
    GoalIncrement,
    MonthlyGoalAdjustment,
)

MONTH_ORDER = [
    'April', 'May', 'June', 'July', 'August', 'September',
    'October', 'November', 'December', 'January', 'February', 'March',
]

MONTH_TO_NUM = {
    'April': 4, 'May': 5, 'June': 6, 'July': 7, 'August': 8,
    'September': 9, 'October': 10, 'November': 11, 'December': 12,
    'January': 1, 'February': 2, 'March': 3,
}

DEFAULT_MONTHLY_GOAL = 3_500_000.0 / 12.0  # ≈ 291,666.67

MIN_FY_YEAR = 2000
MAX_FY_YEAR = 2099


def group_user_filter(user):
    """Return a Q filter that matches all users in the same group, or just this user if ungrouped."""
    if user.group_id:
        return Q(user__group=user.group)
    return Q(user=user)


def fy_date_range(fy_start_year):
    start = datetime.date(fy_start_year, 4, 1)
    end = datetime.date(fy_start_year + 1, 3, 31)
    return start, end


def get_month_date(month_name, fy_start_year):
    num = MONTH_TO_NUM[month_name]
    year = fy_start_year if num >= 4 else fy_start_year + 1
    return datetime.date(year, num, 1)


def resolve_per_month_goals(base_monthly_goal, increments, fy_start_year):
    """
    Given a base monthly goal and a list of GoalIncrement objects,
    return a dict {month_name: effective_goal} for the FY.
    Increments are applied from their effective_month onwards.
    """
    goals = {}
    current = float(base_monthly_goal)
    inc_map = {inc.effective_month: float(inc.increment_amount) for inc in increments}

    for month_name in MONTH_ORDER:
        m_date = get_month_date(month_name, fy_start_year)
        if m_date in inc_map:
            current += inc_map[m_date]
        goals[month_name] = current

    return goals


def apply_monthly_adjustments(per_month_goals, adjustments, fy_start_year):
    """
    Apply one-off MonthlyGoalAdjustment entries on top of the base+increment goals.
    Each adjustment only changes the goal for its specific month.
    """
    adjusted = dict(per_month_goals)

    # Pre-compute mapping from date -> month_name for this FY
    date_to_name = {}
    for month_name in MONTH_ORDER:
        m_date = get_month_date(month_name, fy_start_year)
        date_to_name[m_date] = month_name

    for adj in adjustments:
        month_key = adj.month.replace(day=1)
        month_name = date_to_name.get(month_key)
        if not month_name:
            continue
        adjusted[month_name] = adjusted.get(month_name, 0.0) + float(adj.adjustment_amount)

    return adjusted


def parse_fy_param(raw_value, fallback):
    try:
        val = int(raw_value)
    except (ValueError, TypeError):
        return fallback
    if val < MIN_FY_YEAR or val > MAX_FY_YEAR:
        return fallback
    return val


def get_base_monthly_goal(user):
    """Monthly goal from the latest FY goal on record, else the default."""
    goal_obj = FinancialGoal.objects.filter(group_user_filter(user)).order_by('-month').first()
    return float(goal_obj.monthly_goal) if goal_obj else DEFAULT_MONTHLY_GOAL


def get_fy_increments(user, fy_start_date, fy_end_date):
    gf = group_user_filter(user)
    return GoalIncrement.objects.filter(
        gf,
        effective_month__gte=fy_start_date,
        effective_month__lte=fy_end_date,
    )


def get_fy_adjustments(user, fy_start_date, fy_end_date):
    """Return MonthlyGoalAdjustment objects for the FY across the group."""
    gf = group_user_filter(user)
    return MonthlyGoalAdjustment.objects.filter(
        gf,
        month__gte=fy_start_date,
        month__lte=fy_end_date,
    )


def apply_carry_forward(user, fy_start_date, base_monthly):
    """Add increments from before this FY to the base monthly goal."""
    gf = group_user_filter(user)
    carry = GoalIncrement.objects.filter(
        gf, effective_month__lt=fy_start_date,
    ).aggregate(t=Sum('increment_amount'))['t']
    return base_monthly + float(carry) if carry else base_monthly


def hra_spent(user, fy_start_date, fy_end_date):
    """Total HRA expenses for the FY across the group."""
    spent = HRAExpense.objects.filter(
        group_user_filter(user),
        hra_type='EXPENSE',
        date__gte=fy_start_date,
        date__lte=fy_end_date,
    ).aggregate(t=Sum('amount'))['t']
    return float(spent or 0)


def aggregate_transactions(queryset):
    """Return (net_savings, transfers, income, expense) totals from a transaction queryset."""
    agg = queryset.aggregate(
        savings_pos=Sum(Case(When(type='SAVINGS', then='amount'), default=Value(0), output_field=DecimalField())),
        expense=Sum(Case(When(type='EXPENSE', then='amount'), default=Value(0), output_field=DecimalField())),
        transfers=Sum(Case(When(type='TRANSFER', then='amount'), default=Value(0), output_field=DecimalField())),
        income=Sum(Case(When(type='EXTRA_INCOME', then='amount'), default=Value(0), output_field=DecimalField())),
    )
    gross_expense = float(agg['expense'] or 0)
    net_savings = float(agg['savings_pos'] or 0) - gross_expense
    return net_savings, float(agg['transfers'] or 0), float(agg['income'] or 0), gross_expense
