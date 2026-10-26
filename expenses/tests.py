import base64
import datetime
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from tracker.models import AccountGroup, User

from . import crypto
from .anomaly import apply_flags, evaluate
from .emails import build_summary_context, recipients
from .gmail import GmailAuthError
from .models import (
    CardStatement, Expense, ExpenseCategory, GmailAccount, MerchantRule, PaymentSource, ProcessedEmail, StatementLine,
)
from .parsing import (
    brand_category, classify, mask_sensitive, normalize_merchant, parse_card_payment, parse_statement_lines,
    parse_statement_summary, parse_transaction,
)
from .services import (
    categories_by_name, fy_summary, learn_category, month_summary, monthly_trend, settle_internal_movements,
)
from .ai.schemas import LineMatch
from .statements import due_reminders, find_duplicate, reconcile, record_card_payment, resolve_line
from .sync import ingest_email, sync_account

RECEIVED = datetime.datetime(2026, 3, 5, 10, 0, tzinfo=datetime.timezone.utc)

HDFC_CARD = ('alerts@hdfcbank.net', 'Alert : Update on your HDFC Bank Credit Card',
             'Dear Customer, Thank you for using your HDFC Bank Credit Card ending 8066 for Rs 1,249.00 at '
             'SWIGGY*INSTAMART on 04-03-2026 21:14:05. Authorization code:- 123456')
AXIS_UPI = ('alerts@axisbank.com', 'Debit transaction alert',
            'INR 450.00 debited from A/c no. XX4321 on 03-03-26 for UPI/P2M/412345678901/Zomato Ltd. '
            'Not you? Call 18001035577')
ICICI_CREDIT = ('alerts@icicibank.com', 'Transaction alert',
                'Dear Customer, Your account XX9876 has been credited with Rs 52,000.00 on 01-Mar-26 by NEFT '
                'from ACME CORP. Available balance: Rs 1,00,000')
OTP = ('alerts@hdfcbank.net', 'OTP', 'Your OTP for transaction of Rs 500.00 is 123456. Do not share.')
STATEMENT = ('statements@hdfcbank.net', 'Your HDFC Bank Credit Card Statement for March 2026',
             'Your statement for card ending 8066 is attached. Total Amount Due: Rs 32,450.00 '
             'Minimum Amount Due: Rs 1,630.00 Payment Due Date: 25 Mar 2026')
CARD_PAYMENT = ('alerts@hdfcbank.net', 'Payment received',
                'We have received payment of Rs 32,450.00 towards your HDFC Bank Credit Card ending 8066. Thank you.')
STATEMENT_TEXT = """04/03/2026 SWIGGY INSTAMART BANGALORE 1,249.00
06/03/2026 NETFLIX.COM MUMBAI 649.00
10/03/2026 PAYMENT RECEIVED - THANK YOU 20,000.00 Cr
Total Amount Due 32,450.00"""


class ParserTests(TestCase):
    def test_card_alert(self):
        self.assertEqual(classify(*HDFC_CARD), 'TXN')
        p = parse_transaction(*HDFC_CARD, RECEIVED)
        self.assertEqual(p.amount, Decimal('1249.00'))
        self.assertEqual(p.direction, 'DEBIT')
        self.assertEqual(p.txn_date, datetime.date(2026, 3, 4))
        self.assertEqual(p.txn_time, datetime.time(21, 14, 5))
        self.assertEqual((p.merchant, p.merchant_key), ('Swiggy Instamart', 'SWIGGYINSTAMART'))
        self.assertEqual((p.instrument, p.last4, p.institution), ('CREDIT_CARD', '8066', 'HDFC Bank'))

    def test_upi_debit(self):
        p = parse_transaction(*AXIS_UPI, RECEIVED)
        self.assertEqual((p.amount, p.merchant, p.channel, p.last4), (Decimal('450.00'), 'Zomato', 'UPI', '4321'))

    def test_credit(self):
        p = parse_transaction(*ICICI_CREDIT, RECEIVED)
        self.assertEqual((p.direction, p.amount, p.merchant), ('CREDIT', Decimal('52000.00'), 'Acme'))

    def test_merchant_payment_receipt_is_debit(self):
        gcloud = (
            'google-cloud-compliance@google.com',
            "Google Cloud Platform & APIs: We've received your payment for 01A311-DB1EF5-F7FAD9",
            "Thanks for your payment of Rs 500.00 for Google Cloud Platform. We have received your payment.",
        )
        self.assertEqual(classify(*gcloud), 'TXN')
        p = parse_transaction(*gcloud, RECEIVED)
        self.assertIsNotNone(p)
        self.assertEqual(p.direction, 'DEBIT')
        self.assertEqual(p.amount, Decimal('500.00'))

        airtel = (
            'airtel@airtel.com',
            "Here’s your Airtel payment receipt!",
            "Dear Customer, we have received your payment of Rs 529.82 towards your Airtel broadband bill. Thank you.",
        )
        self.assertEqual(classify(*airtel), 'TXN')
        p2 = parse_transaction(*airtel, RECEIVED)
        self.assertIsNotNone(p2)
        self.assertEqual(p2.direction, 'DEBIT')
        self.assertEqual(p2.amount, Decimal('529.82'))


    def test_otp_and_other_kinds(self):
        self.assertEqual(classify(*OTP), 'IGNORED')
        self.assertEqual(classify(*STATEMENT), 'STATEMENT')
        self.assertEqual(classify(*CARD_PAYMENT), 'CARD_PAYMENT')

    def test_statement_summary(self):
        s = parse_statement_summary(*STATEMENT)
        self.assertEqual((s.total_due, s.min_due), (Decimal('32450.00'), Decimal('1630.00')))
        self.assertEqual((s.due_date, s.last4), (datetime.date(2026, 3, 25), '8066'))

    def test_card_payment(self):
        self.assertEqual(parse_card_payment(*CARD_PAYMENT), (Decimal('32450.00'), '8066', 'HDFC Bank'))

    def test_statement_lines(self):
        lines = parse_statement_lines(STATEMENT_TEXT)
        self.assertEqual([ln.amount for ln in lines], [Decimal('1249.00'), Decimal('649.00'), Decimal('20000.00')])
        self.assertEqual([ln.is_credit for ln in lines], [False, False, True])

    def test_mask_sensitive(self):
        self.assertEqual(mask_sensitive('card 4111111111118066'), 'card XXXXXXXXXXXX8066')

    def test_short_brand_tokens_need_whole_words(self):
        self.assertEqual(normalize_merchant('RELIANCE JIO INFOCOMM'), ('Jio', 'JIO'))
        self.assertEqual(normalize_merchant('LIC OF INDIA')[1], 'LIC')
        for raw in ('SLICE CARD', 'TOYOTA SERVICE', 'BLUE TOKAI COFFEE'):
            display, key = normalize_merchant(raw)
            self.assertIsNone(brand_category(key, f'{display} {raw}'), raw)

    def test_alert_and_statement_share_merchant_key(self):
        self.assertEqual(normalize_merchant('SWIGGY*INSTAMART')[1], normalize_merchant('SWIGGY INSTAMART BLR')[1])


class CryptoTests(SimpleTestCase):
    def test_round_trip_and_tamper(self):
        token = crypto.encrypt('refresh-token-value')
        self.assertNotIn('refresh-token-value', token)
        self.assertEqual(crypto.decrypt(token), 'refresh-token-value')
        self.assertEqual(crypto.decrypt(token[:-4] + 'AAAA'), '')


class ExpenseTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch('expenses.ai.ai_available', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.group = AccountGroup.objects.create(name='Household')
        self.group.config.feature_expenses = True
        self.group.config.save()
        self.user = User.objects.create_user(username='atul', password='pw-123456', user_type='PRIMARY',
                                             group=self.group, email='atul@example.com', first_name='Atul')
        self.spouse = User.objects.create_user(username='riya', password='pw-123456', user_type='ACCOUNT_HOLDER',
                                               group=self.group, email='riya@example.com', first_name='Riya')
        self.cats = categories_by_name(self.group)
        self.account = GmailAccount.objects.create(group=self.group, user=self.user, email='testuser@gmail.com')
        self.account.refresh_token = 'rt'
        self.account.save()

    def email_expense(self, sample=HDFC_CARD, message_id='m1'):
        kind, expense = ingest_email(self.account, message_id, *sample, RECEIVED, cats=self.cats)
        return expense

    def add(self, amount, merchant, date, category=None, **kw):
        _, key = normalize_merchant(merchant)
        return Expense.objects.create(group=self.group, amount=Decimal(amount), merchant=merchant, merchant_key=key,
                                      txn_date=date, category=self.cats.get(category), source=kw.pop('source', 'EMAIL'),
                                      **kw)


class CategorisationTests(ExpenseTestCase):
    def test_brand_category_applied_on_import(self):
        e = self.email_expense()
        self.assertEqual(e.category.name, 'Groceries')
        self.assertEqual(e.category_source, 'KEYWORD')
        self.assertEqual(e.member, self.user)
        self.assertEqual(e.payment_source.last4, '8066')

    def test_learning_refiles_similar_and_applies_to_future(self):
        first = self.email_expense()
        second = self.email_expense(message_id='m2')
        shopping = self.cats['Shopping']
        refiled = learn_category(first, shopping, self.user, apply_to_similar=True)
        self.assertEqual(refiled, 1)
        second.refresh_from_db()
        self.assertEqual((second.category, second.category_source), (shopping, 'RULE'))
        rule = MerchantRule.objects.get(group=self.group, merchant_key='SWIGGYINSTAMART')
        self.assertEqual((rule.category, rule.source), (shopping, 'USER'))
        third = self.email_expense(message_id='m3')
        self.assertEqual((third.category, third.category_source), (shopping, 'RULE'))

    def test_learning_does_not_override_user_choices(self):
        first = self.email_expense()
        second = self.email_expense(message_id='m2')
        learn_category(second, self.cats['Health'], self.user, apply_to_similar=False)
        learn_category(first, self.cats['Shopping'], self.user, apply_to_similar=True)
        second.refresh_from_db()
        self.assertEqual(second.category.name, 'Health')

    def test_manual_category_change_on_ai_expense_does_not_mutate_other_ai_expenses(self):
        """When multiple expenses are categorized by AI, manually editing one expense
        must NOT update other expenses of the same merchant unless explicitly opted in."""
        e1 = self.email_expense(message_id='ai1')
        e2 = self.email_expense(message_id='ai2')
        e3 = self.email_expense(message_id='ai3')
        for e in (e1, e2, e3):
            e.category = self.cats['Food & Dining']
            e.category_source = 'AI'
            e.save()

        health = self.cats['Health']
        # Default behavior: apply_to_similar=False
        refiled = learn_category(e1, health, self.user)
        self.assertEqual(refiled, 0)

        e1.refresh_from_db()
        e2.refresh_from_db()
        e3.refresh_from_db()

        # e1 updated to Health (USER)
        self.assertEqual(e1.category, health)
        self.assertEqual(e1.category_source, 'USER')

        # e2 and e3 remain Food & Dining (AI)
        self.assertEqual(e2.category, self.cats['Food & Dining'])
        self.assertEqual(e2.category_source, 'AI')
        self.assertEqual(e3.category, self.cats['Food & Dining'])
        self.assertEqual(e3.category_source, 'AI')

    def test_expense_edit_view_defaults_remember_to_false(self):
        """Editing an expense via the web UI without 'remember' checked must not touch other expenses."""
        from django.urls import reverse
        e1 = self.email_expense(message_id='edit1')
        e2 = self.email_expense(message_id='edit2')
        for e in (e1, e2):
            e.category = self.cats['Food & Dining']
            e.category_source = 'AI'
            e.save()

        self.client.force_login(self.user)
        response = self.client.post(reverse('expense_edit', args=[e1.pk]), {
            'amount': str(e1.amount),
            'direction': e1.direction,
            'txn_date': e1.txn_date.isoformat(),
            'merchant': e1.merchant,
            'category': self.cats['Shopping'].pk,
        })
        self.assertEqual(response.status_code, 302)

        e1.refresh_from_db()
        e2.refresh_from_db()

        self.assertEqual(e1.category, self.cats['Shopping'])
        self.assertEqual(e1.category_source, 'USER')
        self.assertEqual(e2.category, self.cats['Food & Dining'])
        self.assertEqual(e2.category_source, 'AI')

    def test_transfers_are_not_spend(self):
        self.add('1000', 'Swiggy', datetime.date(2026, 3, 2), 'Food & Dining')
        self.add('50000', 'Zerodha', datetime.date(2026, 3, 3), 'Investments')
        self.add('20000', 'CRED', datetime.date(2026, 3, 4), 'Credit Card Payment')
        s = month_summary(self.group, 2026, 3)
        self.assertEqual(s['total'], Decimal('1000'))
        self.assertEqual(s['transfers'], Decimal('70000'))


class TrendTests(ExpenseTestCase):
    def test_month_in_progress_compares_to_same_day_last_month(self):
        self.add('1000', 'Swiggy', datetime.date(2026, 2, 3), 'Food & Dining')
        self.add('9000', 'Croma', datetime.date(2026, 2, 20), 'Shopping')
        self.add('1500', 'Zomato', datetime.date(2026, 3, 2), 'Food & Dining')
        s = month_summary(self.group, 2026, 3, today=datetime.date(2026, 3, 5))
        self.assertEqual(s['pace']['prev_to_date'], Decimal('1000'))
        self.assertEqual(s['pace']['delta'], Decimal('500'))
        self.assertEqual(s['pace']['projected'], Decimal('10500'))
        food = next(c for c in s['categories'] if c['name'] == 'Food & Dining')
        self.assertEqual(food['delta'], Decimal('500'))
        self.assertIsNone(month_summary(self.group, 2026, 3, today=datetime.date(2026, 4, 2))['pace'])

    def test_day_to_day_figures_ignore_rent(self):
        self.add('30000', 'House Rent', datetime.date(2026, 3, 1), 'Rent & Housing')
        for day in (2, 3):
            self.add('400', 'Zomato', datetime.date(2026, 3, day), 'Food & Dining')
        s = month_summary(self.group, 2026, 3, today=datetime.date(2026, 4, 1))
        self.assertEqual(s['biggest'].merchant, 'Zomato')
        self.assertEqual(s['frequent']['merchant'], 'Zomato')
        self.assertEqual(s['per_day'], Decimal('800') / 31)

    def test_six_month_trend(self):
        self.add('1000', 'A', datetime.date(2025, 11, 5), 'Shopping')
        self.add('3000', 'B', datetime.date(2026, 2, 5), 'Shopping')
        self.add('500', 'C', datetime.date(2026, 3, 2), 'Shopping')
        trend = monthly_trend(self.group, 2026, 3, today=datetime.date(2026, 3, 10))
        self.assertEqual([m['label'] for m in trend['months']], ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'])
        self.assertEqual(trend['months'][-1]['total'], Decimal('500'))
        self.assertTrue(trend['months'][-1]['partial'])
        self.assertEqual(trend['avg'], Decimal('2000'))

    def test_fy_summary_stack_and_previous_year(self):
        self.add('2000', 'A', datetime.date(2025, 5, 10), 'Shopping')
        self.add('3000', 'B', datetime.date(2026, 5, 10), 'Shopping')
        self.add('1000', 'C', datetime.date(2026, 6, 10), 'Groceries')
        s = fy_summary(self.group, 2026, today=datetime.date(2026, 6, 20))
        self.assertEqual(s['prev_total'], Decimal('2000'))
        self.assertEqual(s['prev_delta_pct'], 100)
        self.assertEqual(s['stack'][0]['label'], 'Shopping')
        self.assertEqual(s['stack'][0]['values'][1], 3000.0)
        shopping = s['categories'][0]
        self.assertEqual(shopping['avg_month'], Decimal('1500'))


class SettlementTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.bank = PaymentSource.objects.create(group=self.group, kind='BANK_ACCOUNT', institution='Axis Bank', last4='4321')
        self.other_bank = PaymentSource.objects.create(group=self.group, kind='BANK_ACCOUNT', institution='HDFC Bank', last4='1111')
        self.card = PaymentSource.objects.create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')

    def test_bank_debit_paying_card_bill_is_not_spend(self):
        CardStatement.objects.create(group=self.group, payment_source=self.card, total_due=Decimal('28450'),
                                     statement_date=datetime.date(2026, 3, 1), due_date=datetime.date(2026, 3, 20))
        bill = self.add('28450', 'BillDesk HDFC', datetime.date(2026, 3, 18), payment_source=self.bank)
        self.assertEqual(settle_internal_movements(self.group, datetime.date(2026, 3, 1)), [bill.pk])
        bill.refresh_from_db()
        self.assertEqual((bill.category.name, bill.category_source), ('Credit Card Payment', 'MATCH'))
        self.assertEqual(month_summary(self.group, 2026, 3)['total'], Decimal('0'))

    def test_self_transfer_between_own_accounts(self):
        out = self.add('50000', 'Atul K', datetime.date(2026, 3, 5), payment_source=self.bank)
        into = self.add('50000', 'Atul K', datetime.date(2026, 3, 5), payment_source=self.other_bank, direction='CREDIT')
        settle_internal_movements(self.group, datetime.date(2026, 3, 1))
        out.refresh_from_db()
        into.refresh_from_db()
        self.assertEqual((out.category.name, into.category.name), ('Transfers', 'Transfers'))
        self.assertEqual(evaluate(out), [])

    def test_user_choice_and_card_spend_left_alone(self):
        CardStatement.objects.create(group=self.group, payment_source=self.card, total_due=Decimal('999'),
                                     statement_date=datetime.date(2026, 3, 1))
        mine = self.add('999', 'Amazon', datetime.date(2026, 3, 4), 'Shopping', payment_source=self.bank,
                        category_source='USER')
        on_card = self.add('999', 'Amazon', datetime.date(2026, 3, 4), 'Shopping', payment_source=self.card)
        self.assertEqual(settle_internal_movements(self.group, datetime.date(2026, 3, 1)), [])
        mine.refresh_from_db()
        on_card.refresh_from_db()
        self.assertEqual((mine.category.name, on_card.category.name), ('Shopping', 'Shopping'))

    def test_short_name(self):
        self.assertEqual(self.card.short_name, 'HDFC ••8066')
        self.card.nickname = 'Regalia'
        self.assertEqual(self.card.short_name, 'Regalia')


class AnomalyTests(ExpenseTestCase):
    def test_duplicate_charge(self):
        self.add('999', 'Amazon', datetime.date(2026, 3, 1), 'Shopping')
        dup = self.add('999', 'Amazon', datetime.date(2026, 3, 2), 'Shopping')
        self.assertTrue(any('double charge' in r for r in evaluate(dup)))

    def test_large_for_category(self):
        for day in range(1, 7):
            self.add('400', f'Cafe {day}', datetime.date(2026, 2, day), 'Food & Dining')
        big = self.add('6000', 'Cafe X', datetime.date(2026, 3, 1), 'Food & Dining')
        self.assertTrue(any('usual Food & Dining' in r for r in evaluate(big)))

    def test_foreign_and_review_is_sticky(self):
        e = self.add('20', 'Steam', datetime.date(2026, 3, 1), 'Entertainment', currency='USD')
        apply_flags(e)
        self.assertTrue(e.is_flagged)
        e.flag_reviewed = True
        e.save()
        apply_flags(e)
        self.assertTrue(e.flag_reviewed)

    def test_credits_never_flagged(self):
        e = self.add('90000', 'Acme', datetime.date(2026, 3, 1), direction='CREDIT')
        self.assertEqual(evaluate(e), [])


class ReconcileTests(ExpenseTestCase):
    def make_statement(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        st = CardStatement.objects.create(group=self.group, payment_source=card, status='PARSED',
                                          statement_date=datetime.date(2026, 3, 15),
                                          due_date=datetime.date(2026, 4, 2), total_due=Decimal('1898'))
        StatementLine.objects.bulk_create([
            StatementLine(statement=st, txn_date=ln.txn_date, description=ln.description, amount=ln.amount,
                          is_credit=ln.is_credit)
            for ln in parse_statement_lines(STATEMENT_TEXT)
        ])
        return st

    def test_matches_alerts_and_adds_missing(self):
        alert = self.email_expense()
        st = self.make_statement()
        self.assertEqual(reconcile(st), (1, 1))
        self.assertEqual(st.lines.get(amount=Decimal('1249.00')).matched_expense, alert)
        added = Expense.objects.get(group=self.group, source='STATEMENT')
        self.assertEqual((added.merchant, added.amount, added.category.name), ('Netflix', Decimal('649.00'), 'Subscriptions'))
        self.assertEqual(added.payment_source, alert.payment_source)
        self.assertEqual(reconcile(st), (1, 0))
        self.assertEqual(Expense.objects.filter(source='STATEMENT').count(), 1)

    def test_payment_marks_statement_paid(self):
        self.email_expense()
        st = self.make_statement()
        record_card_payment(self.group, Decimal('1898'), '8066', 'HDFC Bank', datetime.date(2026, 3, 30))
        st.refresh_from_db()
        self.assertTrue(st.is_paid)

    def test_auto_track_statement_payments_multi_part(self):
        from .statements import upcoming_dues
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC', last4='1383')
        st = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            statement_date=datetime.date(2026, 10, 5), due_date=datetime.date(2026, 10, 25),
            total_due=Decimal('20000.00'), is_paid=False,
        )
        # Part 1 payment: ₹8,000 credit on card
        Expense.objects.create(
            group=self.group, payment_source=card, direction='CREDIT', amount=Decimal('8000.00'),
            txn_date=datetime.date(2026, 10, 10), merchant='Credit Card Bill Payment',
        )
        dues = upcoming_dues(self.group, datetime.date(2026, 10, 15))
        st.refresh_from_db()
        self.assertFalse(st.is_paid)
        self.assertEqual(st.paid_amount, Decimal('8000.00'))
        self.assertEqual(dues[0].remaining_due, Decimal('12000.00'))
        self.assertTrue(dues[0].is_partial)

        # Part 2 payment: ₹12,000 credit on card
        Expense.objects.create(
            group=self.group, payment_source=card, direction='CREDIT', amount=Decimal('12000.00'),
            txn_date=datetime.date(2026, 10, 18), merchant='Credit Card Bill Payment',
        )
        dues2 = upcoming_dues(self.group, datetime.date(2026, 10, 19))
        st.refresh_from_db()
        self.assertTrue(st.is_paid)
        self.assertEqual(st.paid_amount, Decimal('20000.00'))
        self.assertEqual(len(dues2), 0)

    def test_due_reminders_windows(self):
        self.email_expense()
        st = self.make_statement()
        self.assertEqual(due_reminders(self.group, datetime.date(2026, 3, 28)), [(st, 5)])
        self.assertEqual(due_reminders(self.group, datetime.date(2026, 3, 29)), [])
        st.reminder_sent_on = datetime.date(2026, 4, 1)
        st.save()
        self.assertEqual(due_reminders(self.group, datetime.date(2026, 4, 1)), [])

    def test_duplicate_statement_sha_and_period(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        st1 = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            pdf_sha256='sha256-sample-hash', statement_date=datetime.date(2026, 3, 15),
            period_end=datetime.date(2026, 3, 15),
        )
        st2 = CardStatement(group=self.group, payment_source=card, pdf_sha256='sha256-sample-hash')
        self.assertEqual(find_duplicate(st2), st1)

        # Same period_end on same card family
        st3 = CardStatement(group=self.group, payment_source=card, period_end=datetime.date(2026, 3, 15))
        self.assertEqual(find_duplicate(st3), st1)

    def test_reconcile_card_family_matching(self):
        # Create an alert under an auto-created card with the same last4
        alt_card = PaymentSource.objects.create(
            group=self.group, kind='CREDIT_CARD', institution='HDFC', last4='8066', is_auto=True,
        )
        alert = Expense.objects.create(
            group=self.group, amount=Decimal('1249.00'), direction='DEBIT',
            merchant='Swiggy Instamart', merchant_key='SWIGGYINSTAMART',
            txn_date=datetime.date(2026, 3, 4), payment_source=alt_card, source='EMAIL',
        )
        st = self.make_statement()
        matched, added = reconcile(st)
        self.assertGreaterEqual(matched, 1)
        line = st.lines.get(amount=Decimal('1249.00'))
        self.assertEqual(line.matched_expense, alert)
        self.assertEqual(line.match_method, 'RULE')

    def test_reconcile_ai_matching_and_parking(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        # Existing expense from alert with different merchant spelling and slightly loose amount
        alert = Expense.objects.create(
            group=self.group, amount=Decimal('500.00'), direction='DEBIT',
            merchant='Amazon Web Services', merchant_key='AWS',
            txn_date=datetime.date(2026, 3, 1), payment_source=card, source='EMAIL',
        )
        st = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            statement_date=datetime.date(2026, 3, 15),
        )
        line = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 6),
            description='AMZN AWS CLOUD SERVICES', amount=Decimal('500.00'), is_credit=False,
        )

        # 1. Test AI confident match
        verdicts = {line.pk: LineMatch(line_id=line.pk, expense_id=alert.pk, confidence=0.95, reason='Amazon cloud service match')}
        with mock.patch('expenses.ai.match_statement_lines', return_value=verdicts):
            reconcile(st)
        line.refresh_from_db()
        self.assertEqual(line.matched_expense, alert)
        self.assertEqual(line.match_method, 'AI')
        self.assertFalse(line.needs_review)

        # 2. Reset and test AI ambiguous / low confidence -> parked for review
        line.matched_expense = None
        line.match_method = ''
        line.save()
        low_verdicts = {line.pk: LineMatch(line_id=line.pk, expense_id=alert.pk, confidence=0.5, reason='Unsure if same transaction')}
        with mock.patch('expenses.ai.match_statement_lines', return_value=low_verdicts):
            reconcile(st)
        line.refresh_from_db()
        self.assertTrue(line.needs_review)
        self.assertEqual(line.suggested_expense, alert)
        st.refresh_from_db()
        self.assertEqual(st.review_count, 1)

    def test_resolve_line(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        alert = Expense.objects.create(
            group=self.group, amount=Decimal('999.00'), direction='DEBIT',
            merchant='Hotstar', merchant_key='HOTSTAR',
            txn_date=datetime.date(2026, 3, 1), payment_source=card, source='EMAIL',
        )
        st = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            statement_date=datetime.date(2026, 3, 15),
        )
        line = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 2),
            description='DISNEY+ HOTSTAR', amount=Decimal('999.00'), is_credit=False,
            needs_review=True, suggested_expense=alert,
        )
        st.review_count = 1
        st.save()

        # Link
        ok = resolve_line(line, 'link')
        self.assertTrue(ok)
        line.refresh_from_db()
        self.assertFalse(line.needs_review)
        self.assertEqual(line.matched_expense, alert)
        self.assertEqual(line.match_method, 'USER')
        st.refresh_from_db()
        self.assertEqual(st.review_count, 0)

        # Add as new
        line2 = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 2),
            description='NEW EXPENSE ENTRY', amount=Decimal('350.00'), is_credit=False,
            needs_review=True, suggested_expense=alert,
        )
        ok2 = resolve_line(line2, 'add')
        self.assertTrue(ok2)
        line2.refresh_from_db()
        self.assertFalse(line2.needs_review)
        self.assertTrue(line2.was_added)
        self.assertIsNotNone(line2.matched_expense)
        self.assertEqual(line2.matched_expense.source, 'STATEMENT')

    def test_partial_payment_accumulation(self):
        st = self.make_statement()
        # First partial payment
        record_card_payment(self.group, Decimal('1000'), '8066', 'HDFC Bank', datetime.date(2026, 3, 20))
        st.refresh_from_db()
        self.assertFalse(st.is_paid)
        self.assertEqual(st.paid_amount, Decimal('1000'))

        # Second payment completing the total due
        record_card_payment(self.group, Decimal('898'), '8066', 'HDFC', datetime.date(2026, 3, 25))
        st.refresh_from_db()
        self.assertTrue(st.is_paid)
        self.assertEqual(st.paid_amount, Decimal('1898'))
        self.assertEqual(st.paid_at, datetime.date(2026, 3, 25))

    def test_resolve_line_enriches_orphan_expense(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        # Expense without payment source
        orphan = Expense.objects.create(
            group=self.group, amount=Decimal('500.00'), direction='DEBIT',
            merchant='Uber', merchant_key='UBER',
            txn_date=datetime.date(2026, 3, 5), payment_source=None, source='MANUAL',
        )
        st = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            statement_date=datetime.date(2026, 3, 15),
        )
        line = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 5),
            description='UBER TRIP', amount=Decimal('500.00'), is_credit=False,
            needs_review=True, suggested_expense=orphan,
        )
        ok = resolve_line(line, 'link')
        self.assertTrue(ok)
        orphan.refresh_from_db()
        self.assertEqual(orphan.payment_source, card)

    def test_duplicate_statement_paid_and_reconcile_views(self):
        card, _ = PaymentSource.objects.get_or_create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        orig = CardStatement.objects.create(
            group=self.group, payment_source=card, status='PARSED',
            statement_date=datetime.date(2026, 3, 15),
        )
        dup = CardStatement.objects.create(
            group=self.group, payment_source=card, status='DUPLICATE',
            duplicate_of=orig, statement_date=datetime.date(2026, 3, 15),
        )
        self.client.force_login(self.user)
        from django.urls import reverse

        # Toggle paid on the duplicate
        resp = self.client.post(reverse('expenses_statement_paid', kwargs={'pk': dup.pk}))
        self.assertEqual(resp.status_code, 302)
        orig.refresh_from_db()
        dup.refresh_from_db()
        self.assertTrue(orig.is_paid)
        self.assertTrue(dup.is_paid)

        # Reconcile on duplicate forwards to original
        resp = self.client.post(reverse('expenses_statement_reconcile', kwargs={'pk': dup.pk}))
        self.assertRedirects(resp, reverse('expenses_statement_detail', kwargs={'pk': orig.pk}))


def _gmail_message(sender, subject, body):
    data = base64.urlsafe_b64encode(body.encode()).decode().rstrip('=')
    return {'id': 'x', 'internalDate': '1772704800000', 'payload': {
        'mimeType': 'text/plain', 'body': {'data': data},
        'headers': [{'name': 'From', 'value': sender}, {'name': 'Subject', 'value': subject},
                    {'name': 'Date', 'value': 'Thu, 05 Mar 2026 10:00:00 +0000'}],
    }}


class SyncTests(ExpenseTestCase):
    def test_ingest_is_idempotent(self):
        self.email_expense()
        kind, expense = ingest_email(self.account, 'm1', *HDFC_CARD, RECEIVED, cats=self.cats)
        self.assertEqual((kind, expense), ('SEEN', None))
        self.assertEqual(Expense.objects.count(), 1)

    def test_otp_recorded_as_ignored(self):
        ingest_email(self.account, 'otp', *OTP, RECEIVED)
        self.assertEqual(ProcessedEmail.objects.get(message_id='otp').kind, 'IGNORED')
        self.assertFalse(Expense.objects.exists())

    def test_statement_email_creates_statement(self):
        ingest_email(self.account, 'st1', *STATEMENT, RECEIVED)
        st = CardStatement.objects.get(gmail_message_id='st1')
        self.assertEqual((st.status, st.total_due, st.payment_source.last4), ('BODY_ONLY', Decimal('32450.00'), '8066'))

    def test_soft_deleted_rows_are_not_reimported(self):
        e = self.email_expense()
        e.is_deleted = True
        e.save()
        ProcessedEmail.objects.all().delete()
        self.email_expense()
        self.assertEqual(Expense.objects.filter(is_deleted=False).count(), 0)

    @mock.patch('expenses.sync.GmailClient')
    def test_sync_account(self, client_cls):
        client = client_cls.return_value
        client.list_message_ids.return_value = ['a', 'b', 'c']
        client.get_message.side_effect = lambda mid: _gmail_message(*{'a': HDFC_CARD, 'b': AXIS_UPI, 'c': OTP}[mid])
        result = sync_account(self.account)
        self.assertEqual((result.transactions, result.ignored, result.complete), (2, 1, True))
        self.account.refresh_from_db()
        self.assertIsNotNone(self.account.last_synced_at)
        self.assertEqual(sync_account(self.account).transactions, 0)

    @mock.patch('expenses.sync.GmailClient')
    def test_revoked_token_deactivates(self, client_cls):
        client_cls.return_value.list_message_ids.side_effect = GmailAuthError('revoked')
        result = sync_account(self.account)
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_active)
        self.assertTrue(self.account.needs_reconnect)
        self.assertEqual(result.error, 'revoked')

    @mock.patch('expenses.sync.GmailClient')
    def test_backfill_statements(self, client_cls):
        client = client_cls.return_value
        client.list_message_ids.return_value = ['st_msg_1']
        msg = {
            'id': 'st_msg_1', 'internalDate': '1772704800000',
            'payload': {
                'mimeType': 'multipart/mixed',
                'headers': [
                    {'name': 'From', 'value': STATEMENT[0]},
                    {'name': 'Subject', 'value': STATEMENT[1]},
                    {'name': 'Date', 'value': 'Thu, 05 Mar 2026 10:00:00 +0000'},
                ],
                'parts': [
                    {'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(STATEMENT[2].encode()).decode()}},
                    {'mimeType': 'application/pdf', 'filename': 'statement.pdf', 'body': {'attachmentId': 'att1'}},
                ],
            },
        }
        client.get_message.return_value = msg
        client.get_attachment.return_value = b'%PDF-mock-data'

        with mock.patch('expenses.statements.read_pdf') as mock_read:
            def fake_read(st, data, password=''):
                st.status = 'PARSED'
                st.line_count = 2
                st.matched_count = 1
                st.added_count = 1
                st.save()
            mock_read.side_effect = fake_read

            call_command('backfill_statements', since='2026-01-01', stdout=mock.MagicMock())
            st = CardStatement.objects.get(gmail_message_id='st_msg_1')
            self.assertEqual(st.status, 'PARSED')
            self.assertEqual(st.line_count, 2)


class ViewTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.expense = self.email_expense()

    def test_pages_render(self):
        for name, args in [('expenses_home', []), ('expenses_year', []), ('expenses_settings', []),
                           ('expenses_statements', [])]:
            resp = self.client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, 200, name)
        resp = self.client.get(reverse('expenses_home') + '?m=2026-03')
        self.assertContains(resp, 'Swiggy Instamart')

    def test_spouse_can_view_and_edit(self):
        self.client.force_login(self.spouse)
        self.assertEqual(self.client.get(reverse('expenses_home')).status_code, 200)
        resp = self.client.post(reverse('expense_edit', args=[self.expense.pk]), {
            'amount': '1249', 'direction': 'DEBIT', 'txn_date': '2026-03-04', 'merchant': 'Swiggy Instamart',
            'category': self.cats['Food & Dining'].pk, 'remember': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.category_source, 'USER')

    def test_landlord_forbidden_and_feature_toggle(self):
        landlord = User.objects.create_user(username='ll', password='pw-123456', user_type='LANDLORD', group=self.group)
        self.client.force_login(landlord)
        self.assertEqual(self.client.get(reverse('expenses_home')).status_code, 403)
        self.client.force_login(self.user)
        self.group.config.feature_expenses = False
        self.group.config.save()
        self.assertEqual(self.client.get(reverse('expenses_home')).status_code, 404)

    def test_other_household_cannot_touch(self):
        other = AccountGroup.objects.create(name='Other')
        intruder = User.objects.create_user(username='x', password='pw-123456', user_type='PRIMARY', group=other)
        self.client.force_login(intruder)
        resp = self.client.post(reverse('expense_delete', args=[self.expense.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_add_manual_and_learn(self):
        resp = self.client.post(reverse('expense_add'), {
            'amount': '300', 'direction': 'DEBIT', 'txn_date': '2026-03-06', 'merchant': 'Ramesh Dairy',
            'category': self.cats['Groceries'].pk, 'remember': 'on',
        })
        self.assertEqual(resp.status_code, 302)
        e = Expense.objects.get(merchant='Ramesh Dairy')
        self.assertEqual((e.source, e.member, e.created_by), ('MANUAL', self.user, self.user))
        self.assertTrue(MerchantRule.objects.filter(merchant_key=e.merchant_key, source='USER').exists())

    def test_invalid_amount_rejected(self):
        self.client.post(reverse('expense_add'), {'amount': '-5', 'direction': 'DEBIT', 'txn_date': '2026-03-06',
                                                  'merchant': 'X'})
        self.assertFalse(Expense.objects.filter(merchant='X').exists())

    def test_delete_soft_for_imported_hard_for_manual(self):
        self.client.post(reverse('expense_delete', args=[self.expense.pk]))
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.is_deleted)
        manual = self.add('100', 'Chai', datetime.date(2026, 3, 1), source='MANUAL')
        self.client.post(reverse('expense_delete', args=[manual.pk]))
        self.assertFalse(Expense.objects.filter(pk=manual.pk).exists())

    def test_review_flag(self):
        self.expense.is_flagged = True
        self.expense.save()
        self.client.post(reverse('expense_review', args=[self.expense.pk]))
        self.expense.refresh_from_db()
        self.assertTrue(self.expense.flag_reviewed)

    def test_gmail_callback_rejects_bad_state(self):
        session = self.client.session
        session['expenses_gmail_oauth_state'] = 'good'
        session.save()
        with mock.patch('expenses.views.gmail.exchange_code') as exchange:
            resp = self.client.get(reverse('expenses_gmail_callback'), {'state': 'bad', 'code': 'c'})
        self.assertRedirects(resp, reverse('expenses_settings'), fetch_redirect_response=False)
        exchange.assert_not_called()

    @mock.patch('expenses.views.gmail.revoke')
    def test_disconnect_keeps_expenses(self, revoke):
        self.client.post(reverse('expenses_gmail_disconnect', args=[self.account.pk]))
        revoke.assert_called_once()
        self.assertFalse(GmailAccount.objects.exists())
        self.assertTrue(Expense.objects.filter(pk=self.expense.pk).exists())

    def test_category_delete_uncategorises(self):
        cat = self.expense.category
        self.client.post(reverse('expenses_category_delete', args=[cat.pk]))
        self.expense.refresh_from_db()
        self.assertIsNone(self.expense.category)
        self.assertFalse(ExpenseCategory.objects.filter(pk=cat.pk).exists())

    def test_statement_detail_and_paid_toggle(self):
        st = CardStatement.objects.create(group=self.group, payment_source=self.expense.payment_source,
                                          due_date=datetime.date(2026, 4, 2), total_due=Decimal('1249'))
        self.assertEqual(self.client.get(reverse('expenses_statement_detail', args=[st.pk])).status_code, 200)
        self.client.post(reverse('expenses_statement_paid', args=[st.pk]))
        st.refresh_from_db()
        self.assertTrue(st.is_paid)

    def test_statement_line_resolve_view(self):
        st = CardStatement.objects.create(group=self.group, payment_source=self.expense.payment_source,
                                          due_date=datetime.date(2026, 4, 2), total_due=Decimal('1249'))
        line = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 4),
            description='Test Resolve Line', amount=Decimal('500.00'), is_credit=False,
            needs_review=True, suggested_expense=self.expense,
        )
        st.review_count = 1
        st.save()

        # Link action
        resp = self.client.post(reverse('expenses_statement_line_resolve', args=[line.pk]), {'action': 'link'})
        self.assertRedirects(resp, reverse('expenses_statement_detail', args=[st.pk]))
        line.refresh_from_db()
        self.assertFalse(line.needs_review)
        self.assertEqual(line.matched_expense, self.expense)

        # Add action
        line2 = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 3, 4),
            description='Second Resolve Line', amount=Decimal('600.00'), is_credit=False,
            needs_review=True, suggested_expense=self.expense,
        )
        resp2 = self.client.post(reverse('expenses_statement_line_resolve', args=[line2.pk]), {'action': 'add'})
        self.assertRedirects(resp2, reverse('expenses_statement_detail', args=[st.pk]))
        line2.refresh_from_db()
        self.assertFalse(line2.needs_review)
        self.assertTrue(line2.was_added)


def _pdf(password=None, pages=1):
    import io
    from pypdf import PdfWriter
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class SecurityTests(ExpenseTestCase):
    def test_locked_statement_pdf_is_encrypted_at_rest(self):
        from .statements import read_pdf
        card = PaymentSource.objects.create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        st = CardStatement.objects.create(group=self.group, payment_source=card)
        data = _pdf(password='ATUL0101')
        read_pdf(st, data)
        st.refresh_from_db()
        self.assertEqual(st.status, 'NEEDS_PASSWORD')
        self.assertNotIn(b'%PDF', bytes(st.pdf_blob))
        self.assertEqual(crypto.decrypt_bytes(st.pdf_blob), data)

    def test_pdf_page_cap(self):
        from .statements import MAX_PDF_PAGES, pdf_text
        with mock.patch('pypdf._page.PageObject.extract_text', return_value='x') as extract:
            pdf_text(_pdf(pages=MAX_PDF_PAGES + 5))
        self.assertEqual(extract.call_count, MAX_PDF_PAGES)

    def test_email_subject_is_masked(self):
        sample = (HDFC_CARD[0], 'Alert for card 4111111111118066', HDFC_CARD[2])
        e = self.email_expense(sample)
        self.assertNotIn('411111111111', e.email_subject)

    def _investment(self):
        return self.add('25000', 'Zerodha', datetime.date(2026, 3, 1), 'Investments')

    def test_spouse_cannot_see_investment_debits(self):
        inv = self._investment()
        self.client.force_login(self.spouse)
        page = self.client.get(reverse('expenses_home') + '?m=2026-03').content.decode()
        self.assertNotIn('Zerodha', page)
        resp = self.client.post(reverse('expense_delete', args=[inv.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(month_summary(self.group, 2026, 3, hide_investments=True)['transfers'], Decimal('0'))

    def test_primary_still_sees_investments(self):
        self._investment()
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('expenses_home') + '?m=2026-03'), 'Zerodha')

    def test_household_email_leaves_out_investments(self):
        self._investment()
        ctx = build_summary_context(self.group, 2026, 3, with_ai=False)
        self.assertEqual(ctx['summary']['transfers'], Decimal('0'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailTests(ExpenseTestCase):
    def test_summary_counts_only_mail_transactions(self):
        self.email_expense()
        self.add('5000', 'Cash to maid', datetime.date(2026, 3, 3), 'Household & Services', source='MANUAL')
        ctx = build_summary_context(self.group, 2026, 3, with_ai=False)
        self.assertEqual(ctx['summary']['total'], Decimal('1249.00'))
        html = render_to_string('emails/expense_summary.html', ctx)
        self.assertIn('Swiggy Instamart', html)
        self.assertNotIn('Cash to maid', html)

    def test_foreign_flags_reach_the_email(self):
        e = self.add('20', 'OpenAI', datetime.date(2026, 3, 2), 'Subscriptions', currency='USD')
        apply_flags(e)
        ctx = build_summary_context(self.group, 2026, 3, with_ai=False)
        self.assertEqual(ctx['flagged'], [e])

    def test_recipients_are_household_members(self):
        self.assertEqual(recipients(self.group), ['atul@example.com', 'riya@example.com'])

    def test_summary_command_sends_with_flags(self):
        e = self.email_expense()
        e.is_flagged, e.flag_reasons = True, ['Possible double charge']
        e.save()
        call_command('send_expense_summary', month='2026-03', stdout=mock.MagicMock())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('1 to review', mail.outbox[0].subject)
        self.assertIn('Possible double charge', mail.outbox[0].alternatives[0][0])

    def test_reminder_command(self):
        card = PaymentSource.objects.create(group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='8066')
        today = datetime.date.today()
        st = CardStatement.objects.create(group=self.group, payment_source=card, total_due=Decimal('5000'),
                                          due_date=today + datetime.timedelta(days=1))
        with mock.patch('expenses.management.commands.expense_reminders.timezone.localdate', return_value=today):
            call_command('expense_reminders', stdout=mock.MagicMock())
            call_command('expense_reminders', stdout=mock.MagicMock())
        self.assertEqual(len(mail.outbox), 1)
        st.refresh_from_db()
        self.assertEqual(st.reminder_sent_on, today)


class ExpensesAITests(SimpleTestCase):
    def test_prompt_builders(self):
        from .ai.prompts import (
            build_categorise_prompt, build_extract_prompt,
            build_monthly_note_prompt, build_statement_prompt,
        )

        cat_prompt = build_categorise_prompt(
            [{'id': 1, 'merchant': 'Uber', 'amount': 250.0}],
            ['Transport', 'Food & Dining'],
            [('Uber', 'Transport')],
        )
        self.assertIn('Allowed categories:', cat_prompt)
        self.assertIn('Transport', cat_prompt)
        self.assertIn('Uber', cat_prompt)

        ext_prompt = build_extract_prompt('Alert', 'A/c 12345678 debited by Rs 500')
        self.assertIn('Subject: Alert', ext_prompt)
        self.assertNotIn('12345678', ext_prompt)  # Sensitive account masked

        st_prompt = build_statement_prompt('01/03/2026 SWIGGY 500.00')
        self.assertIn('SWIGGY', st_prompt)

        note_prompt = build_monthly_note_prompt({'total_spend': 50000})
        self.assertIn('50000', note_prompt)

    @mock.patch('expenses.ai.runner.gateway.generate_structured')
    @mock.patch('expenses.ai.runner.ai_available', return_value=True)
    def test_categorise_runner(self, mock_avail, mock_gen):
        from .ai import CategoryBatch, CategoryChoice, categorise

        mock_gen.return_value = CategoryBatch(
            results=[CategoryChoice(id=42, category='Groceries', confidence=0.95)]
        )
        res = categorise(
            [{'id': 42, 'merchant': 'Blinkit', 'amount': 400.0}],
            ['Groceries', 'Transport'],
            [],
        )
        self.assertEqual(res, {42: ('Groceries', 0.95)})

    @mock.patch('expenses.ai.runner.gateway.generate_structured')
    @mock.patch('expenses.ai.runner.ai_available', return_value=True)
    def test_extract_transaction_runner(self, mock_avail, mock_gen):
        from .ai import ExtractedTxn, extract_transaction

        mock_gen.return_value = ExtractedTxn(
            is_transaction=True, amount=1249.0, merchant='Swiggy', direction='DEBIT'
        )
        res = extract_transaction('Swiggy Order', 'Debited INR 1249 for Swiggy')
        self.assertIsNotNone(res)
        self.assertEqual(res.amount, 1249.0)
        self.assertEqual(res.merchant, 'Swiggy')


class BrandKnowledgeTests(TestCase):
    def setUp(self):
        super().setUp()
        from .knowledge import ensure_seed_knowledge

        ensure_seed_knowledge()

    def test_seed_and_lookup(self):
        from .knowledge import ensure_seed_knowledge, lookup_brand
        from .models import BrandKnowledge

        ensure_seed_knowledge()
        self.assertTrue(BrandKnowledge.objects.filter(merchant_key='SWIGGY').exists())
        swiggy = lookup_brand('SWIGGY')
        self.assertIsNotNone(swiggy)
        self.assertEqual(swiggy[0], 'Swiggy')
        self.assertEqual(swiggy[1], 'Food & Dining')
        self.assertEqual(swiggy[2], 'delivery_dining')

    def test_ai_expansion(self):
        from .knowledge import lookup_brand, record_ai_brand

        entry = record_ai_brand(
            merchant_key='CHAIPOINT',
            display_name='Chai Point',
            category_name='Food & Dining',
            icon='coffee',
            confidence=0.9,
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry.source, 'AI')

        looked_up = lookup_brand('CHAIPOINT')
        self.assertIsNotNone(looked_up)
        self.assertEqual(looked_up[0], 'Chai Point')
        self.assertEqual(looked_up[1], 'Food & Dining')
        self.assertEqual(looked_up[2], 'coffee')

    def test_category_template_and_proxy(self):
        from .categories import DEFAULT_CATEGORIES
        from .knowledge import get_category_hue, get_category_icon, get_category_templates
        from .models import CategoryTemplate

        templates = get_category_templates()
        self.assertGreaterEqual(len(templates), 20)
        self.assertGreaterEqual(len(DEFAULT_CATEGORIES), 20)
        self.assertEqual(CategoryTemplate.objects.count(), len(templates))

        icon = get_category_icon('Food & Dining')
        self.assertEqual(icon, 'restaurant')
        hue = get_category_hue('Food & Dining')
        self.assertEqual(hue, 20)

    def test_keyword_knowledge_and_resolution(self):
        from .models import KeywordKnowledge
        from .parsing import brand_category, brand_icon

        self.assertTrue(KeywordKnowledge.objects.filter(keyword='ATM').exists())
        self.assertEqual(brand_category('UNKNOWNXYZ', 'Payment for ATM cash'), 'Cash Withdrawal')
        self.assertEqual(brand_icon('UNKNOWNXYZ', 'Payment for ATM cash'), 'local_atm')

    def test_ensure_default_categories_populates_group(self):
        from tracker.models import AccountGroup
        from .categories import ensure_default_categories
        from .models import CategoryTemplate, ExpenseCategory

        grp = AccountGroup.objects.create(name='Knowledge Test Group')
        ensure_default_categories(grp)
        group_cats = ExpenseCategory.objects.filter(group=grp)
        self.assertEqual(group_cats.count(), CategoryTemplate.objects.count())


class ExpenseAuditCooldownTests(ExpenseTestCase):
    def test_audit_cooldown_allows_first_run(self):
        from .anomaly import audit_cooldown_status
        status = audit_cooldown_status(self.group)
        self.assertTrue(status['can_audit'])
        self.assertIsNone(status['latest_run'])

    def test_audit_cooldown_blocks_within_seven_days(self):
        import datetime
        from django.utils import timezone
        from .anomaly import audit_cooldown_status
        from .models import ExpenseAuditRun

        # Create an audit run 2 days ago
        two_days_ago = timezone.now() - datetime.timedelta(days=2)
        run = ExpenseAuditRun.objects.create(
            group=self.group,
            run_by=self.user,
            expenses_scanned=20,
            anomalies_flagged=1,
            flagged_ids=[101],
        )
        ExpenseAuditRun.objects.filter(pk=run.pk).update(created_at=two_days_ago)

        status = audit_cooldown_status(self.group)
        self.assertFalse(status['can_audit'])
        self.assertEqual(status['remaining_days'], 4)
        self.assertIsNotNone(status['next_available'])

    def test_audit_cooldown_allows_after_seven_days(self):
        import datetime
        from django.utils import timezone
        from .anomaly import audit_cooldown_status
        from .models import ExpenseAuditRun

        # Create an audit run 8 days ago
        eight_days_ago = timezone.now() - datetime.timedelta(days=8)
        run = ExpenseAuditRun.objects.create(
            group=self.group,
            run_by=self.user,
            expenses_scanned=20,
            anomalies_flagged=0,
        )
        ExpenseAuditRun.objects.filter(pk=run.pk).update(created_at=eight_days_ago)

        status = audit_cooldown_status(self.group)
        self.assertTrue(status['can_audit'])

    def test_ai_audit_view_enforces_cooldown(self):
        import datetime
        from django.urls import reverse
        from django.utils import timezone
        from .models import ExpenseAuditRun

        run = ExpenseAuditRun.objects.create(
            group=self.group,
            run_by=self.user,
            expenses_scanned=10,
            anomalies_flagged=0,
        )
        one_day_ago = timezone.now() - datetime.timedelta(days=1)
        ExpenseAuditRun.objects.filter(pk=run.pk).update(created_at=one_day_ago)

        self.client.force_login(self.user)
        # Attempt to run audit while cooldown is active
        response = self.client.post(reverse('expenses_ai_audit'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('?flagged=1', response.url)

        # Count of audit runs should still be 1 (no new run created)
        self.assertEqual(ExpenseAuditRun.objects.filter(group=self.group).count(), 1)


class RefundAndEmiTrackingTests(TestCase):
    def setUp(self):
        from tracker.models import AccountGroup, User
        self.group = AccountGroup.objects.create(name='Test Household')
        self.user = User.objects.create_user(username='tester', email='t@example.com', password='pw')
        self.group.members.add(self.user)
        self.card = PaymentSource.objects.create(
            group=self.group, kind='CREDIT_CARD', institution='HDFC Bank', last4='2555', owner=self.user,
        )

    def test_refund_matching_deducts_net_spend(self):
        from .analytics import month_summary
        from .models import Expense
        from .statements import reconcile_refunds

        # Purchase on Oct 16
        debit = Expense.objects.create(
            group=self.group,
            amount=Decimal('82954.00'),
            direction='DEBIT',
            txn_date=datetime.date(2026, 10, 16),
            merchant='MakeMyTrip',
            merchant_key='MAKEMYTRIP',
            payment_source=self.card,
        )
        # Refund on Oct 7
        credit = Expense.objects.create(
            group=self.group,
            amount=Decimal('82954.00'),
            direction='CREDIT',
            txn_date=datetime.date(2026, 10, 7),
            merchant='MakeMyTrip',
            merchant_key='MAKEMYTRIP',
            payment_source=self.card,
        )

        linked = reconcile_refunds(self.group)
        self.assertEqual(linked, 1)

        debit.refresh_from_db()
        credit.refresh_from_db()

        self.assertEqual(credit.refund_of_id, debit.pk)
        self.assertEqual(debit.refunded_amount, Decimal('82954.00'))
        self.assertEqual(debit.refund_date, datetime.date(2026, 10, 7))
        self.assertTrue(debit.is_fully_refunded)
        self.assertEqual(debit.net_amount, Decimal('0.00'))
        self.assertFalse(debit.is_spend)

        # In month_summary, net spend should be 0, and refunded_total should be 82954
        summary = month_summary(self.group, 2026, 10)
        self.assertEqual(summary['total'], Decimal('0.00'))
        self.assertEqual(summary['gross_total'], Decimal('82954.00'))
        self.assertEqual(summary['refunded_total'], Decimal('82954.00'))
        self.assertEqual(summary['refund_count'], 1)

    def test_partial_refund_calculates_net_spend(self):
        from .analytics import month_summary
        from .models import Expense
        from .statements import reconcile_refunds

        debit = Expense.objects.create(
            group=self.group,
            amount=Decimal('1000.00'),
            direction='DEBIT',
            txn_date=datetime.date(2026, 10, 5),
            merchant='Meesho',
            merchant_key='MEESHO',
            payment_source=self.card,
        )
        Expense.objects.create(
            group=self.group,
            amount=Decimal('400.00'),
            direction='CREDIT',
            txn_date=datetime.date(2026, 10, 10),
            merchant='Meesho',
            merchant_key='MEESHO',
            payment_source=self.card,
        )

        reconcile_refunds(self.group)
        debit.refresh_from_db()

        self.assertEqual(debit.refunded_amount, Decimal('400.00'))
        self.assertEqual(debit.net_amount, Decimal('600.00'))
        self.assertTrue(debit.is_spend)

        summary = month_summary(self.group, 2026, 10)
        self.assertEqual(summary['total'], Decimal('600.00'))
        self.assertEqual(summary['gross_total'], Decimal('1000.00'))

    def test_emi_parsing_and_analytics_grouping(self):
        from .analytics import month_summary
        from .models import Expense
        from .parsing import parse_emi_details

        p_info = parse_emi_details('OFFUS EMI,PRIN NB:03,XXXXXXXXXX9861 (Ref# 123)')
        self.assertTrue(p_info['is_emi'])
        self.assertEqual(p_info['component'], 'PRINCIPAL')
        self.assertEqual(p_info['installment_num'], 3)
        self.assertEqual(p_info['reference'], '9861')

        i_info = parse_emi_details('OFFUS EMI,INT NBR:03,XXXXXXXXXX9861 (Ref# 124)')
        self.assertTrue(i_info['is_emi'])
        self.assertEqual(i_info['component'], 'INTEREST')
        self.assertEqual(i_info['installment_num'], 3)

        v_info = parse_emi_details('EMI VIJAY SALES INDIA PRI')
        self.assertTrue(v_info['is_emi'])
        self.assertEqual(v_info['component'], 'PURCHASE')

        # Create EMI expense rows
        Expense.objects.create(
            group=self.group, amount=Decimal('3475.00'), direction='DEBIT',
            txn_date=datetime.date(2026, 10, 23), merchant='Loan ••9861 (Principal #3)',
            is_emi=True, emi_component='PRINCIPAL', emi_installment_num=3, emi_reference='9861',
            payment_source=self.card,
        )
        Expense.objects.create(
            group=self.group, amount=Decimal('395.00'), direction='DEBIT',
            txn_date=datetime.date(2026, 10, 23), merchant='Loan ••9861 (Interest #3)',
            is_emi=True, emi_component='INTEREST', emi_installment_num=3, emi_reference='9861',
            payment_source=self.card,
        )
        Expense.objects.create(
            group=self.group, amount=Decimal('83000.00'), direction='DEBIT',
            txn_date=datetime.date(2026, 10, 19), merchant='Vijay Sales (EMI)',
            is_emi=True, emi_component='PURCHASE',
            payment_source=self.card,
        )

        summary = month_summary(self.group, 2026, 10)
        emi_data = summary['emi_summary']
        self.assertEqual(emi_data['count'], 3)
        self.assertEqual(len(emi_data['ongoing']), 1)
        # 3475 + 395 = 3870
        self.assertEqual(emi_data['ongoing'][0]['total'], Decimal('3870.00'))
        self.assertEqual(emi_data['monthly_commitment'], Decimal('3870.00'))
        # Initially total_installments is None, so pending is None
        self.assertIsNone(emi_data['ongoing'][0]['total_installments'])
        self.assertIsNone(emi_data['ongoing'][0]['pending_installments'])

        # Set tenure via view
        self.client.force_login(self.user)
        response = self.client.post(reverse('expense_set_emi_tenure'), {
            'ref': '9861',
            'total_installments': '12',
            'installment_num': '3',
        })
        self.assertEqual(response.status_code, 302)

        # Check that month_summary now reflects total & pending installments (12 - 3 = 9)
        summary2 = month_summary(self.group, 2026, 10)
        emi2 = summary2['emi_summary']['ongoing'][0]
        self.assertEqual(emi2['total_installments'], 12)
        self.assertEqual(emi2['pending_installments'], 9)

    def test_bppy_cc_payments_skipped_in_reconcile(self):
        from .models import CardStatement, StatementLine
        from .statements import _is_payment, reconcile

        self.assertTrue(_is_payment('BPPY CC PAYMENT DPXXXXXXXX3739S9aoA (Ref#STXXXXXXXXXXXXXXXXX6401)'))
        self.assertTrue(_is_payment('UPICC-26-09-2026-XXXXXXXX6139 +'))
        self.assertFalse(_is_payment('MAKEMYTRIP INDIA PVTNEW DELHI (Ref# VTXXXXXXXXXXXXXXXXX0134)'))
        self.assertFalse(_is_payment('AtlysMumbai (Ref# VTXXXXXXXXXXXXXXXXX0075)'))

        st = CardStatement.objects.create(
            group=self.group, payment_source=self.card, statement_date=datetime.date(2026, 10, 23),
            status='BODY_ONLY',
        )
        line = StatementLine.objects.create(
            statement=st, txn_date=datetime.date(2026, 9, 25),
            description='BPPY CC PAYMENT DPXXXXXXXX3739S9aoA',
            amount=Decimal('50000.00'), is_credit=True,
        )
        reconcile(st)
        line.refresh_from_db()
        self.assertEqual(line.match_method, 'SKIP')
        self.assertFalse(line.was_added)
        self.assertIsNone(line.matched_expense)

    def test_toggle_emi_on_expense(self):
        from .forms import ExpenseForm

        e = Expense.objects.create(
            group=self.group,
            amount=Decimal('5000.00'),
            direction='DEBIT',
            txn_date=datetime.date(2026, 10, 15),
            merchant='Some Store',
            is_emi=True,
            emi_component='PURCHASE',
        )

        # Toggle is_emi off via form edit
        data = {
            'amount': '5000.00',
            'direction': 'DEBIT',
            'txn_date': '2026-10-15',
            'merchant': 'Some Store',
            'is_emi': False,
        }
        form = ExpenseForm(data, instance=e, group=self.group)
        self.assertTrue(form.is_valid())
        saved = form.save()
        self.assertFalse(saved.is_emi)

    def test_refunds_filter_excludes_credit_card_payments(self):
        # Create an actual refund
        refund = Expense.objects.create(
            group=self.group, amount=Decimal('500.00'), direction='CREDIT',
            txn_date=datetime.date(2026, 10, 10), merchant='Amazon Refund',
        )
        # Create a credit card bill payment credit receipt
        card_payment = Expense.objects.create(
            group=self.group, amount=Decimal('22958.00'), direction='CREDIT',
            txn_date=datetime.date(2026, 10, 10), merchant='Credit Card Bill Payment',
            payment_source=self.card,
        )
        cats = categories_by_name(self.group)
        card_payment.category = cats.get('Credit Card Payment')
        card_payment.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('expenses_home') + '?m=2026-10&refunds=1')
        self.assertEqual(response.status_code, 200)
        items = [e for day in response.context['days'] for e in day['items']]
        self.assertIn(refund, items)
        self.assertNotIn(card_payment, items)

    def test_modular_refund_q_and_aggregation(self):
        from .analytics import all_refunds_q, credit_refunds_q, month_summary
        from .models import Expense

        refund_credit = Expense.objects.create(
            group=self.group, amount=Decimal('500.00'), direction='CREDIT',
            txn_date=datetime.date(2026, 10, 12), merchant='Amazon Return',
        )
        bill_credit = Expense.objects.create(
            group=self.group, amount=Decimal('5000.00'), direction='CREDIT',
            txn_date=datetime.date(2026, 10, 12), merchant='Credit Card Bill Payment',
            payment_source=self.card,
        )
        self.card.kind = 'CREDIT_CARD'
        self.card.save()

        matched_credits = list(Expense.objects.filter(group=self.group).filter(credit_refunds_q()))
        self.assertIn(refund_credit, matched_credits)
        self.assertNotIn(bill_credit, matched_credits)

        all_matched = list(Expense.objects.filter(group=self.group).filter(all_refunds_q()))
        self.assertIn(refund_credit, all_matched)
        self.assertNotIn(bill_credit, all_matched)

        summary = month_summary(self.group, 2026, 10)
        self.assertIn('gross_total', summary)
        self.assertIn('refunded_total', summary)

    def test_expense_set_emi_tenure_security_and_validation(self):
        from .models import Expense
        exp = Expense.objects.create(
            group=self.group, amount=Decimal('1000.00'), direction='DEBIT',
            txn_date=datetime.date(2026, 10, 1), merchant='EMI Test',
            is_emi=True, emi_reference='SEC99',
        )
        self.client.force_login(self.user)

        # 1. Open redirect attack attempt: should not redirect to external host
        resp = self.client.post(reverse('expense_set_emi_tenure'), {
            'ref': 'SEC99',
            'expense_id': str(exp.pk),
            'total_installments': '12',
            'installment_num': '2',
            'next': 'https://evil.com/phish',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('evil.com', resp.url)
        self.assertTrue(resp.url.endswith(reverse('expenses_home')))

        # 2. Integer out of smallint bounds (e.g. 999999): should be rejected safely without 500 error
        resp = self.client.post(reverse('expense_set_emi_tenure'), {
            'ref': 'SEC99',
            'expense_id': str(exp.pk),
            'total_installments': '9999999',
            'installment_num': '9999999',
        })
        self.assertEqual(resp.status_code, 302)
        exp.refresh_from_db()
        self.assertNotEqual(exp.emi_total_installments, 9999999)

    def test_crypto_fernet_lru_caching(self):
        from .crypto import _fernet, decrypt, encrypt

        f1 = _fernet()
        f2 = _fernet()
        self.assertIs(f1, f2)
        token = encrypt('secret-payload')
        self.assertEqual(decrypt(token), 'secret-payload')

    def test_model_meta_indexes(self):
        from .models import CardStatement, Expense

        exp_index_names = [idx.name for idx in Expense._meta.indexes]
        self.assertIn('exp_grp_del_date_idx', exp_index_names)
        self.assertIn('exp_grp_emi_ref_idx', exp_index_names)

        st_index_names = [idx.name for idx in CardStatement._meta.indexes]
        self.assertIn('st_grp_paid_due_idx', st_index_names)
        self.assertIn('st_grp_status_idx', st_index_names)

    def test_partial_card_statement_payment_tracking(self):
        from .categories import categories_by_name
        from .models import CardStatement, Expense, PaymentSource
        from .statements import upcoming_dues

        card2 = PaymentSource.objects.create(
            group=self.group, kind='CREDIT_CARD', institution='HDFC', last4='2555',
        )
        st = CardStatement.objects.create(
            group=self.group, payment_source=card2, total_due=Decimal('571780.00'),
            statement_date=datetime.date(2026, 9, 20), due_date=datetime.date(2026, 10, 10),
            is_paid=False,
        )

        cats = categories_by_name(self.group)
        transfer_cat = cats.get('Transfers')

        # Credit of 4.3L received on card2 on 26 Oct (today)
        credit = Expense.objects.create(
            group=self.group, amount=Decimal('430000.00'), direction='CREDIT',
            txn_date=datetime.date(2026, 10, 26), merchant='Unknown merchant',
            payment_source=card2, category=transfer_cat,
        )

        # Debit from bank of 4.3L
        Expense.objects.create(
            group=self.group, amount=Decimal('430000.00'), direction='DEBIT',
            txn_date=datetime.date(2026, 10, 26), merchant='VPA club@axisb',
            category=transfer_cat,
        )

        dues = upcoming_dues(self.group, today=datetime.date(2026, 10, 26))
        st.refresh_from_db()
        credit.refresh_from_db()

        self.assertEqual(st.paid_amount, Decimal('430000.00'))
        self.assertFalse(st.is_paid)
        self.assertEqual(len(dues), 1)
        self.assertTrue(dues[0].is_partial)
        self.assertEqual(dues[0].remaining_due, Decimal('141780.00'))
        self.assertEqual(credit.merchant, 'Credit Card Bill Payment')
        self.assertEqual(credit.category.name, 'Credit Card Payment')

        self.client.force_login(self.user)
        response = self.client.get(reverse('expenses_home') + '?m=2026-10')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_dues_amount'], Decimal('141780.00'))
        self.assertNotContains(response, '>AI Audit</')






