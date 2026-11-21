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


class TrackerSecurityHardeningTests(TestCase):
    def setUp(self):
        from tracker.models import HRAExpense, Note, Transaction
        self.group = AccountGroup.objects.create(name="SecHome")
        self.other_group = AccountGroup.objects.create(name="OtherHome")
        self.owner = User.objects.create_user(
            username="sec_owner", password="pw", user_type="PRIMARY", group=self.group
        )
        self.spouse = User.objects.create_user(
            username="sec_spouse", password="pw", user_type="ACCOUNT_HOLDER", group=self.group
        )
        self.outsider = User.objects.create_user(
            username="sec_outsider", password="pw", user_type="PRIMARY", group=self.other_group
        )
        self.txn = Transaction.objects.create(
            user=self.owner, date=datetime.date(2026, 5, 10),
            amount=Decimal('1000'), remarks="Home Txn", type="SAVINGS",
        )
        self.other_txn = Transaction.objects.create(
            user=self.outsider, date=datetime.date(2026, 5, 10),
            amount=Decimal('2000'), remarks="Other Txn", type="SAVINGS",
        )
        self.hra = HRAExpense.objects.create(
            user=self.owner, date=datetime.date(2026, 5, 10),
            amount=Decimal('15000'), expense_type="Rent", hra_type="EXPENSE", mode_of_payment="UPI",
        )
        self.other_hra = HRAExpense.objects.create(
            user=self.outsider, date=datetime.date(2026, 5, 10),
            amount=Decimal('15000'), expense_type="Rent", hra_type="EXPENSE", mode_of_payment="UPI",
        )
        self.spouse_note = Note.objects.create(
            user=self.spouse, title="Private Spouse Note", body="Secret",
            date=datetime.date(2026, 5, 10), financial_year=2026,
        )

    def test_disabled_savings_feature_blocks_all_mutations(self):
        self.group.config.feature_savings = False
        self.group.config.save()
        self.client.force_login(self.owner)

        endpoints = [
            ('POST', '/add/', {'date': '2026-05-10', 'amount': '500', 'type': 'SAVINGS', 'remarks': 'x'}),
            ('POST', f'/edit/{self.txn.pk}/', {'date': '2026-05-10', 'amount': '600', 'type': 'SAVINGS'}),
            ('POST', f'/delete/{self.txn.pk}/', {}),
            ('POST', '/goal/increment/', {'effective_month': '2026-06-01', 'increment_amount': '5000'}),
            ('POST', '/goal/annual/2026/', {'annual_goal': '1200000'}),
            ('POST', '/goal/adjustment/', {'month': '2026-06-01', 'adjustment_amount': '2000'}),
            ('POST', '/month-comment/', {'month': '2026-06-01', 'comment': 'test'}),
        ]
        for _, url, data in endpoints:
            resp = self.client.post(url, data)
            self.assertEqual(resp.status_code, 404, url)

    def test_disabled_hra_feature_blocks_hra_mutations(self):
        self.group.config.feature_hra = False
        self.group.config.save()
        self.client.force_login(self.owner)

        self.assertEqual(self.client.post('/hra/add/', {
            'date': '2026-05-10', 'amount': '5000', 'hra_type': 'EXPENSE', 'mode_of_payment': 'UPI'
        }).status_code, 404)
        self.assertEqual(self.client.post(f'/hra/edit/{self.hra.pk}/', {}).status_code, 404)
        self.assertEqual(self.client.post(f'/hra/delete/{self.hra.pk}/').status_code, 404)

    def test_cross_household_idor_and_private_note_isolation(self):
        self.client.force_login(self.owner)
        # Cross-household transaction & HRA IDOR -> 404
        self.assertEqual(self.client.post(f'/edit/{self.other_txn.pk}/', {}).status_code, 404)
        self.assertEqual(self.client.post(f'/delete/{self.other_txn.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/hra/edit/{self.other_hra.pk}/', {}).status_code, 404)
        self.assertEqual(self.client.post(f'/hra/delete/{self.other_hra.pk}/').status_code, 404)
        # Spouse private note cannot be edited or deleted even by PRIMARY in same household
        self.assertEqual(self.client.post(f'/notes/edit/{self.spouse_note.pk}/', {
            'title': 'Hijack', 'body': 'x', 'date': '2026-05-10'
        }).status_code, 404)
        self.assertEqual(self.client.post(f'/notes/delete/{self.spouse_note.pk}/').status_code, 404)

    def test_month_comment_rejects_overlong_input_without_500(self):
        from tracker.models import MonthlySavingsComment
        self.client.force_login(self.owner)
        resp = self.client.post('/month-comment/', {
            'month': '2026-06-15',
            'comment': 'x' * 600,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(MonthlySavingsComment.objects.filter(user=self.owner).exists())


class LegacyHRADecouplingTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="DecoupleHome")
        self.owner = User.objects.create_user(
            username="dec_owner", password="x", user_type="PRIMARY", group=self.group
        )
        self.landlord = User.objects.create_user(
            username="dec_landlord", password="x", user_type="LANDLORD", group=self.group
        )

    def test_current_fy_2026_excludes_transfers_and_hra_from_savings_and_ui(self):
        from tracker.models import HRAExpense

        d26 = datetime.date(2026, 5, 10)
        Transaction.objects.create(user=self.owner, date=d26, amount=Decimal('50000'), type='SAVINGS')
        Transaction.objects.create(user=self.owner, date=d26, amount=Decimal('10000'), type='EXTRA_INCOME')
        Transaction.objects.create(user=self.owner, date=d26, amount=Decimal('5000'), type='EXPENSE')
        Transaction.objects.create(user=self.owner, date=d26, amount=Decimal('20000'), type='TRANSFER')
        HRAExpense.objects.create(
            user=self.owner, date=d26, amount=Decimal('15000'),
            expense_type='Rent', hra_type='EXPENSE', mode_of_payment='UPI',
        )

        self.client.force_login(self.owner)
        resp = self.client.get('/?fy=2026')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['goal_achieved'], 55000.0)
        self.assertIsNone(resp.context['hra_balance'])
        self.assertFalse(resp.context['use_legacy_hra'])

        html = resp.content.decode()
        self.assertNotIn('HRA Balance', html)
        self.assertNotIn('<div class="v-stat-label">Transfers</div>', html)

    def test_new_transactions_reject_transfer_while_legacy_transfer_edits_succeed(self):
        self.client.force_login(self.owner)

        resp = self.client.post('/transactions/add/', {
            'date': '2026-06-01',
            'amount': '12000',
            'type': 'TRANSFER',
            'remarks': 'Should not be allowed',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Transaction.objects.filter(user=self.owner, type='TRANSFER').exists())

        legacy_txn = Transaction.objects.create(
            user=self.owner,
            date=datetime.date(2026, 4, 15),
            amount=Decimal('20000'),
            type='TRANSFER',
            remarks='Old transfer',
        )
        edit_resp = self.client.post(f'/transactions/edit/{legacy_txn.pk}/', {
            'date': '2026-04-15',
            'amount': '20000',
            'type': 'TRANSFER',
            'remarks': 'Old transfer updated',
        })
        self.assertEqual(edit_resp.status_code, 302)
        legacy_txn.refresh_from_db()
        self.assertEqual(legacy_txn.type, 'TRANSFER')
        self.assertEqual(legacy_txn.remarks, 'Old transfer updated')

    def test_previous_fy_2025_preserves_legacy_hra_and_transfers_calculation(self):
        from tracker.models import HRAExpense

        d25 = datetime.date(2025, 5, 10)
        Transaction.objects.create(user=self.owner, date=d25, amount=Decimal('50000'), type='SAVINGS')
        Transaction.objects.create(user=self.owner, date=d25, amount=Decimal('10000'), type='EXTRA_INCOME')
        Transaction.objects.create(user=self.owner, date=d25, amount=Decimal('5000'), type='EXPENSE')
        Transaction.objects.create(user=self.owner, date=d25, amount=Decimal('20000'), type='TRANSFER')
        HRAExpense.objects.create(
            user=self.owner, date=d25, amount=Decimal('15000'),
            expense_type='Rent', hra_type='EXPENSE', mode_of_payment='UPI',
        )

        self.client.force_login(self.owner)
        resp = self.client.get('/?fy=2025')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['use_legacy_hra'])
        self.assertEqual(resp.context['hra_balance'], 5000.0)
        self.assertEqual(resp.context['goal_achieved'], 60000.0)

        html = resp.content.decode()
        self.assertIn('HRA Balance', html)
        self.assertIn('<div class="v-stat-label">Transfers</div>', html)

    def test_hra_page_renders_deprecation_banner_for_primary_and_landlord(self):
        for u in (self.owner, self.landlord):
            self.client.force_login(u)
            resp = self.client.get('/hra/')
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, 'will be discarded shortly')



