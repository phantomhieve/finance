import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from tracker.models import AccountGroup, MonthlySavingsComment, Transaction, User
from tracker.services import fy_date_range
from tracker.views import _savings_pace

FY = 2026
FY_START, FY_END = fy_date_range(FY)
MONTHS = [{'goal': 100_000.0} for _ in range(12)]  # ₹12 L annual goal


class SavingsPaceTests(TestCase):
    def test_open_fy_prorates_current_month_and_spreads_remaining_need(self):
        # 15 Jun: April + May done (2 L) and half of June (0.5 L) expected
        pace = _savings_pace(MONTHS, 200_000.0, 1_200_000.0, datetime.date(2026, 6, 15), FY_START, FY_END)
        self.assertEqual(pace['state'], 'open')
        self.assertAlmostEqual(pace['gap'], -50_000.0)
        self.assertEqual(pace['months_left'], 10)
        self.assertAlmostEqual(pace['need_per_month'], 100_000.0)

    def test_ahead_of_pace_and_goal_already_met(self):
        pace = _savings_pace(MONTHS, 1_300_000.0, 1_200_000.0, datetime.date(2026, 4, 30), FY_START, FY_END)
        self.assertGreater(pace['gap'], 0)
        self.assertEqual(pace['need_per_month'], 0)

    def test_closed_and_future_fy(self):
        closed = _savings_pace(MONTHS, 1_100_000.0, 1_200_000.0, datetime.date(2027, 5, 1), FY_START, FY_END)
        self.assertEqual((closed['state'], closed['hit'], closed['gap_abs']), ('closed', False, 100_000.0))
        self.assertIsNone(_savings_pace(MONTHS, 0, 1_200_000.0, datetime.date(2026, 1, 1), FY_START, FY_END))


class SavingsDashboardTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Home")
        self.owner = User.objects.create_user(username="owner", password="x", user_type="PRIMARY", group=self.group)
        self.spouse = User.objects.create_user(username="sp", password="x", user_type="ACCOUNT_HOLDER", group=self.group)
        self.month = timezone.now().date().replace(day=1)

    def test_lists_every_transaction_in_the_fy(self):
        Transaction.objects.bulk_create([
            Transaction(user=self.owner, amount=Decimal('1000'), date=self.month, type='SAVINGS') for _ in range(60)
        ])
        self.client.force_login(self.owner)
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['transactions']), 60)
        self.assertContains(resp, '₹1,000')

    def test_month_comment_is_visible_to_the_whole_household(self):
        MonthlySavingsComment.objects.create(user=self.owner, month=self.month, comment="Car repair")
        self.client.force_login(self.spouse)
        resp = self.client.get('/')
        self.assertTrue(any(m['comment'] == "Car repair" for m in resp.context['monthly_data']))


class HouseholdAccessTests(TestCase):
    def setUp(self):
        import time
        self.group = AccountGroup.objects.create(name="Home")
        self.spouse = User.objects.create_user(username="sp2", password="x", user_type="ACCOUNT_HOLDER", group=self.group)
        self.client.force_login(self.spouse)
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

    def test_account_holder_gets_jewellery_but_not_portfolio(self):
        self.assertTrue(self.group.config.feature_jewellery)
        self.assertEqual(self.client.get('/jewellery/').status_code, 200)
        self.assertEqual(self.client.get('/portfolio/').status_code, 403)
        self.assertEqual(self.client.get('/portfolio/growth/').status_code, 403)
        self.assertNotIn('href="/portfolio/"', self.client.get('/').content.decode())

    def test_only_primary_opens_portfolio(self):
        import time
        landlord = User.objects.create_user(username="ll2", password="x", user_type="LANDLORD", group=self.group)
        self.client.force_login(landlord)
        self.assertEqual(self.client.get('/portfolio/').status_code, 403)
        primary = User.objects.create_user(username="pr2", password="x", user_type="PRIMARY", group=self.group)
        self.client.force_login(primary)
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()
        self.assertEqual(self.client.get('/portfolio/').status_code, 200)

    def test_dock_hides_disabled_modules(self):
        config = self.group.config
        config.feature_jewellery = False
        config.feature_notes = False
        config.save()
        html = self.client.get('/').content.decode()
        self.assertNotIn('href="/jewellery/"', html)
        self.assertNotIn('href="/notes/"', html)
        self.assertIn('href="/hra/"', html)


class NotesSecurityAndFeatureTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Home")
        self.owner = User.objects.create_user(username="owner_n", password="x", user_type="PRIMARY", group=self.group)
        self.other_group = AccountGroup.objects.create(name="Other")
        self.other_user = User.objects.create_user(username="other_n", password="x", user_type="PRIMARY", group=self.other_group)

    def test_unauthenticated_note_endpoints_redirect_to_login(self):
        self.assertEqual(self.client.get('/notes/').status_code, 302)
        self.assertEqual(self.client.post('/notes/add/', {'title': 'Secret'}).status_code, 302)
        self.assertEqual(self.client.post('/notes/edit/1/', {'title': 'Edit'}).status_code, 302)
        self.assertEqual(self.client.post('/notes/delete/1/').status_code, 302)
        self.assertEqual(self.client.post('/notes/toggle-todo/1/').status_code, 302)

    def test_feature_disabled_blocks_all_note_actions(self):
        config = self.group.config
        config.feature_notes = False
        config.save()

        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/notes/').status_code, 404)
        self.assertEqual(self.client.post('/notes/add/', {'title': 'Blocked'}).status_code, 404)
        self.assertEqual(self.client.post('/notes/edit/1/', {'title': 'Blocked'}).status_code, 404)
        self.assertEqual(self.client.post('/notes/delete/1/').status_code, 404)
        self.assertEqual(self.client.post('/notes/toggle-todo/1/').status_code, 404)

    def test_note_crud_and_tenant_isolation(self):
        from tracker.models import Note
        self.client.force_login(self.owner)

        # 1. Add Note
        resp = self.client.post('/notes/add/', {
            'title': 'Emergency Fund Checklist',
            'section': 'General',
            'content': 'Keep 6 months in liquid FD.',
            'date': '2026-06-01',
            'financial_year': 2026,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        note = Note.objects.filter(user=self.owner, title='Emergency Fund Checklist').first()
        self.assertIsNotNone(note)
        self.assertEqual(note.section, 'General')

        # 2. Edit Note
        resp = self.client.post(f'/notes/edit/{note.pk}/', {
            'title': 'Emergency Fund Checklist Updated',
            'section': 'General',
            'content': 'Keep 9 months in liquid FD.',
            'date': '2026-06-01',
            'financial_year': 2026,
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.title, 'Emergency Fund Checklist Updated')

        # 3. Cross-Tenant Edit Blocked (other user cannot edit owner's note)
        self.client.force_login(self.other_user)
        resp = self.client.post(f'/notes/edit/{note.pk}/', {'title': 'Hacked'}, follow=True)
        self.assertEqual(resp.status_code, 404)
        note.refresh_from_db()
        self.assertEqual(note.title, 'Emergency Fund Checklist Updated')

        # 4. Delete Note
        self.client.force_login(self.owner)
        resp = self.client.post(f'/notes/delete/{note.pk}/', follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Note.objects.filter(pk=note.pk).exists())

    def test_todo_toggle_logic_and_ajax_contract(self):
        from tracker.models import Note
        self.client.force_login(self.owner)

        todo = Note.objects.create(
            user=self.owner,
            title='Review Insurance Policy',
            section='Todo',
            date=datetime.date(2026, 6, 1),
            financial_year=2026,
            is_done=False,
        )

        # Standard POST toggle
        self.client.post(f'/notes/toggle-todo/{todo.pk}/')
        todo.refresh_from_db()
        self.assertTrue(todo.is_done)
        self.assertIsNotNone(todo.done_at)

        # AJAX POST toggle back to undone
        resp = self.client.post(
            f'/notes/toggle-todo/{todo.pk}/',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'ok': True, 'is_done': False})
        todo.refresh_from_db()
        self.assertFalse(todo.is_done)
        self.assertIsNone(todo.done_at)


class TransactionAndHRATests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Home")
        self.owner = User.objects.create_user(username="owner_tx", password="x", user_type="PRIMARY", group=self.group)
        self.spouse = User.objects.create_user(username="sp_tx", password="x", user_type="ACCOUNT_HOLDER", group=self.group)
        self.landlord = User.objects.create_user(username="ll_tx", password="x", user_type="LANDLORD", group=self.group)
        self.today = timezone.localdate()

    def test_account_holder_cannot_add_or_delete_savings_transactions(self):
        self.client.force_login(self.spouse)
        resp = self.client.post('/transactions/add/', {
            'date': str(self.today),
            'amount': '15000',
            'type': 'SAVINGS',
        })
        self.assertEqual(resp.status_code, 403)

    def test_primary_adds_and_deletes_transaction(self):
        self.client.force_login(self.owner)
        resp = self.client.post('/transactions/add/', {
            'date': str(self.today),
            'amount': '25000',
            'type': 'SAVINGS',
            'remarks': 'Monthly SIP savings',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        txn = Transaction.objects.filter(user=self.owner, amount=Decimal('25000')).first()
        self.assertIsNotNone(txn)

        # Delete transaction
        resp = self.client.post(f'/transactions/delete/{txn.pk}/', follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Transaction.objects.filter(pk=txn.pk).exists())

    def test_hra_tracker_and_balance_calculation(self):
        from tracker.models import HRAExpense
        self.client.force_login(self.owner)

        # Add Rent Paid (Addition)
        HRAExpense.objects.create(
            user=self.owner,
            date=self.today,
            amount=Decimal('40000'),
            hra_type='RENT_PAID',
            mode_of_payment='Net Banking',
        )
        # Add HRA Expense
        HRAExpense.objects.create(
            user=self.owner,
            date=self.today,
            amount=Decimal('15000'),
            hra_type='EXPENSE',
            mode_of_payment='UPI',
        )

        resp = self.client.get('/hra/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_expense'], 15000.0)
        self.assertEqual(resp.context['total_additions'], 40000.0)
        self.assertEqual(resp.context['remaining_balance'], 25000.0)

    def test_landlord_views_hra_only(self):
        self.client.force_login(self.landlord)
        self.assertEqual(self.client.get('/hra/').status_code, 200)
        self.assertEqual(self.client.get('/').status_code, 302)  # Redirects to /hra/
        self.assertEqual(self.client.get('/notes/').status_code, 403)


class GoalAndCarryForwardTests(TestCase):
    def setUp(self):
        from tracker.services import apply_carry_forward, resolve_per_month_goals, apply_monthly_adjustments
        self.group = AccountGroup.objects.create(name="Home")
        self.owner = User.objects.create_user(username="owner_g", password="x", user_type="PRIMARY", group=self.group)
        self.apply_carry_forward = apply_carry_forward
        self.resolve_per_month_goals = resolve_per_month_goals
        self.apply_monthly_adjustments = apply_monthly_adjustments

    def test_carry_forward_increments_prior_to_fy(self):
        from tracker.models import GoalIncrement
        GoalIncrement.objects.create(
            user=self.owner,
            effective_month=datetime.date(2025, 10, 1),
            increment_amount=Decimal('15000'),
        )
        base = 100000.0
        carried = self.apply_carry_forward(self.owner, datetime.date(2026, 4, 1), base)
        self.assertEqual(carried, 115000.0)

    def test_resolve_per_month_goals_and_adjustments(self):
        from tracker.models import GoalIncrement, MonthlyGoalAdjustment
        increments = [
            GoalIncrement(effective_month=datetime.date(2026, 7, 1), increment_amount=Decimal('10000'))
        ]
        goals = self.resolve_per_month_goals(100000.0, increments, 2026)
        self.assertEqual(goals['April'], 100000.0)
        self.assertEqual(goals['June'], 100000.0)
        self.assertEqual(goals['July'], 110000.0)
        self.assertEqual(goals['March'], 110000.0)

        adjustments = [
            MonthlyGoalAdjustment(month=datetime.date(2026, 8, 1), adjustment_amount=Decimal('5000'))
        ]
        adjusted_goals = self.apply_monthly_adjustments(goals, adjustments, 2026)
        self.assertEqual(adjusted_goals['August'], 115000.0)
        self.assertEqual(adjusted_goals['September'], 110000.0)

