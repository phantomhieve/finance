import datetime

from django.db import migrations, models


def _fy_start_year(d):
    return d.year if d.month >= 4 else d.year - 1


def _fy_label(start):
    return f"FY {start}-{str(start + 1)[-2:]}"


def backfill(apps, schema_editor):
    FinancialGoal = apps.get_model('portfolio', 'FinancialGoal')
    MonthlySnapshot = apps.get_model('portfolio', 'MonthlySnapshot')
    today = datetime.date.today()
    current_fy = _fy_start_year(today)

    march_close = {
        (s.group_id, s.month.year - 1): s.total_current_value
        for s in MonthlySnapshot.objects.filter(month__month=3)
    }

    for goal in FinancialGoal.objects.all():
        changed = []
        if not goal.financial_year and goal.target_date:
            goal.financial_year = _fy_label(_fy_start_year(goal.target_date))
            changed.append('financial_year')

        fy = goal.financial_year or ''
        if fy.startswith('FY ') and goal.closing_value is None:
            try:
                start = int(fy[3:7])
            except ValueError:
                start = None
            if start is not None and start < current_fy:
                closing = march_close.get((goal.group_id, start))
                if closing is not None:
                    goal.closing_value = closing
                    changed.append('closing_value')
        if changed:
            goal.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0019_alter_financialgoal_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='financialgoal',
            name='closing_value',
            field=models.DecimalField(
                blank=True, decimal_places=0, max_digits=14, null=True,
                help_text='Portfolio value at FY close (from the March snapshot); locks the achieved/missed verdict',
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
