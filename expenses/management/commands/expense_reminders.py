from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from expenses.emails import build_reminder_context, recipients
from expenses.models import CardStatement
from expenses.statements import due_reminders
from portfolio.emails import send_html_email
from portfolio.templatetags.indian_format import inr
from tracker.models import AccountGroup


class Command(BaseCommand):
    help = 'Emails credit card bill reminders 5 days, 1 day and on the due date (and while overdue).'

    def handle(self, *args, **options):
        today = timezone.localdate()
        group_ids = CardStatement.objects.filter(is_paid=False, due_date__isnull=False).values_list('group_id', flat=True)
        sent = 0
        for group in AccountGroup.objects.filter(pk__in=set(group_ids)):
            config = getattr(group, 'config', None)
            if config is not None and not config.feature_expenses:
                continue
            to = recipients(group)
            if not to:
                continue
            for statement, days_left in due_reminders(group, today):
                ctx = build_reminder_context(statement, days_left)
                when = ('is overdue' if days_left < 0 else 'is due today' if days_left == 0
                        else f'is due in {days_left} day{"s" if days_left != 1 else ""}')
                amount = f' — {inr(statement.total_due)}' if statement.total_due else ''
                subject = f"{ctx['card']} bill {when}{amount}"
                text = f"{subject}\nDue date: {statement.due_date:%d %b %Y}\n{ctx['app_url']}"
                try:
                    send_html_email(subject, text, render_to_string('emails/expense_reminder.html', ctx), to)
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f'Reminder for statement {statement.pk} failed: {exc}'))
                    continue
                statement.reminder_sent_on = today
                statement.save(update_fields=['reminder_sent_on'])
                sent += 1
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} bill reminder(s).'))
