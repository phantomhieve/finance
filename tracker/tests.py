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
