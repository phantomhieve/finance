import datetime
import json
import time
from decimal import Decimal
from unittest import mock

from django.test import TestCase, Client
from django.urls import reverse

from tracker.models import AccountGroup, User
from portfolio.models import RealEstateHolding, MonthlySnapshot
from portfolio.services import get_portfolio_summary, take_monthly_snapshot
from mcp_server import server as mcp_srv


class RealEstateModelTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Test Family")
        self.holding = RealEstateHolding.objects.create(
            group=self.group,
            name="Sector 150 Express Plot",
            property_type="PLOT_LAND",
            status="VACANT_PLOT",
            area_value=Decimal("200"),
            area_unit="GAJ",
            locality="Sector 150",
            city="Noida",
            state="Uttar Pradesh",
            landmark="Near Sports City & Expressway",
            pincode="201310",
            micro_market_tag="Noida Expressway Corridor",
            purchase_date=datetime.date(2023, 1, 15),
            purchase_price=Decimal("10000000"),
            stamp_duty_charges=Decimal("700000"),
            current_valuation=Decimal("16000000"),
            monthly_rental_income=Decimal("0"),
        )

    def test_unit_conversions(self):
        # 200 Gaj -> 200 Gaj, 1800 sq ft
        self.assertEqual(self.holding.area_in_gaj, Decimal("200"))
        self.assertEqual(self.holding.area_in_sqft, Decimal("1800"))
        self.assertIn("200 Gaj", self.holding.area_display)

        # Sq ft holding
        sqft_holding = RealEstateHolding(area_value=Decimal("1800"), area_unit="SQFT")
        self.assertEqual(sqft_holding.area_in_gaj, Decimal("200.00"))
        self.assertEqual(sqft_holding.area_in_sqft, Decimal("1800"))

        # Acre holding
        acre_holding = RealEstateHolding(area_value=Decimal("1"), area_unit="ACRE")
        self.assertEqual(acre_holding.area_in_gaj, Decimal("4840.00"))
        self.assertEqual(acre_holding.area_in_sqft, Decimal("43560.00"))

    def test_financial_calculations(self):
        # Total cost basis = 1 Cr + 7 Lakh = 1.07 Cr
        self.assertEqual(self.holding.total_cost_basis, Decimal("10700000"))
        self.assertEqual(self.holding.purchase_value, Decimal("10700000"))
        self.assertEqual(self.holding.current_value, Decimal("16000000"))

        # P&L = 16,000,000 - 10,700,000 = 5,300,000
        self.assertEqual(self.holding.pnl, Decimal("5300000"))
        self.assertTrue(self.holding.pnl_pct > Decimal("49.00"))

        # Rates per Gaj
        # Purchase rate = 10,000,000 / 200 = 50,000 / Gaj
        self.assertEqual(self.holding.purchase_rate_per_gaj, Decimal("50000.00"))
        # Current rate = 16,000,000 / 200 = 80,000 / Gaj
        self.assertEqual(self.holding.current_rate_per_gaj, Decimal("80000.00"))

        # Rental yield when rented
        self.holding.monthly_rental_income = Decimal("40000")
        self.assertEqual(self.holding.annual_rental_income, Decimal("480000"))
        # 480,000 / 16,000,000 * 100 = 3.00%
        self.assertEqual(self.holding.rental_yield_pct, Decimal("3.00"))

    def test_llm_research_prompt(self):
        prompt = self.holding.get_llm_research_prompt()
        self.assertIn("Sector 150 Express Plot", prompt)
        self.assertIn("Sector 150, Noida, Uttar Pradesh", prompt)
        self.assertIn("200 Gaj", prompt)
        self.assertIn("circle rates", prompt)


class RealEstateViewsTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Family Group")
        self.group.set_portfolio_password("pass123")
        self.group.save()

        self.user = User.objects.create_user(
            username="investor",
            password="securepassword",
            user_type="PRIMARY",
            group=self.group,
        )

        self.client = Client()
        self.client.login(username="investor", password="securepassword")

        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

    def test_real_estate_detail_page_loads(self):
        response = self.client.get(reverse('real_estate_detail'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Real Estate Investments")
        self.assertContains(response, "Total Real Estate Valuation")

    def test_add_and_edit_real_estate(self):
        post_data = {
            'name': 'ATS Greens Apartment 404',
            'property_type': 'APARTMENT_FLAT',
            'status': 'RENTED',
            'acquisition_type': 'PURCHASED',
            'area_value': '150',
            'area_unit': 'GAJ',
            'locality': 'Sector 150',
            'city': 'Noida',
            'state': 'Uttar Pradesh',
            'landmark': 'Near Metro',
            'pincode': '201310',
            'micro_market_tag': 'Expressway',
            'google_maps_url': 'https://maps.app.goo.gl/example',
            'khasra_khata_number': 'Flat 404 Tower A',
            'purchase_date': '2024-02-01',
            'purchase_price': '8500000',
            'stamp_duty_charges': '550000',
            'current_valuation': '11000000',
            'last_valuation_date': '2026-01-01',
            'monthly_rental_income': '35000',
            'remarks': '3BHK rented to IT family',
        }
        res = self.client.post(reverse('add_real_estate'), data=post_data)
        self.assertEqual(res.status_code, 302)

        self.assertEqual(RealEstateHolding.objects.count(), 1)
        prop = RealEstateHolding.objects.first()
        self.assertEqual(prop.name, 'ATS Greens Apartment 404')
        self.assertEqual(prop.group, self.group)
        self.assertEqual(prop.total_cost_basis, Decimal('9050000'))
        self.assertEqual(prop.current_valuation, Decimal('11000000'))

        # Test Valuation Update view
        val_data = {
            'current_valuation': '12500000',
            'last_valuation_date': '2026-03-01',
            'monthly_rental_income': '38000',
            'remarks': 'Appraisal updated after new metro corridor announcement',
        }
        res_val = self.client.post(reverse('update_real_estate_valuation', kwargs={'pk': prop.pk}), data=val_data)
        self.assertEqual(res_val.status_code, 302)

        prop.refresh_from_db()
        self.assertEqual(prop.current_valuation, Decimal('12500000'))
        self.assertEqual(prop.monthly_rental_income, Decimal('38000'))

        # Test Prompt JSON AJAX view
        res_json = self.client.get(reverse('real_estate_llm_prompt_json', kwargs={'pk': prop.pk}))
        self.assertEqual(res_json.status_code, 200)
        data = res_json.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn("ATS Greens Apartment 404", data['prompt'])

        # Test Delete
        res_del = self.client.post(reverse('delete_real_estate', kwargs={'pk': prop.pk}))
        self.assertEqual(res_del.status_code, 302)
        self.assertEqual(RealEstateHolding.objects.count(), 0)

    def test_portfolio_summary_and_snapshot(self):
        RealEstateHolding.objects.create(
            group=self.group,
            name="Yamuna Plot 22D",
            property_type="PLOT_LAND",
            area_value=Decimal("300"),
            area_unit="GAJ",
            locality="Sector 22D",
            city="Greater Noida",
            purchase_date=datetime.date(2023, 6, 1),
            purchase_price=Decimal("6000000"),
            stamp_duty_charges=Decimal("400000"),
            current_valuation=Decimal("9500000"),
        )
        summary = get_portfolio_summary(self.group)
        self.assertEqual(summary['real_estate_invested'], Decimal('6400000'))
        self.assertEqual(summary['real_estate_current'], Decimal('9500000'))
        self.assertEqual(summary['real_estate_returns'], Decimal('3100000'))

        # Check in asset classes list
        re_asset = next(a for a in summary['assets'] if a['name'] == 'Real Estate')
        self.assertEqual(re_asset['value'], Decimal('9500000'))

        # Take snapshot
        snap, created = take_monthly_snapshot(group=self.group)
        self.assertIsNotNone(snap)
        self.assertIn('real_estate', snap.data)
        self.assertEqual(snap.data['real_estate']['current'], 9500000.0)


class RealEstateMcpServerTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="MCP Group")
        self.user = User.objects.create_user(
            username="mcptester",
            password="mcppassword",
            user_type="PRIMARY",
            group=self.group,
        )
        # Point MCP server context to test group
        mcp_srv._get_group = lambda: self.group

    def test_mcp_real_estate_flow(self):
        # 1. Add holding via MCP
        res = mcp_srv.add_real_estate_holding(
            name="Jewar Airport Commercial Corridor",
            area_value="500",
            purchase_date="2023-11-10",
            purchase_price="15000000",
            current_valuation="22000000",
            property_type="COMMERCIAL",
            status="RESALE_PLANNED",
            area_unit="GAJ",
            locality="Yamuna Expressway Sector 29",
            city="Greater Noida",
            state="Uttar Pradesh",
            landmark="Near Cargo Hub",
            stamp_duty_charges="1050000",
            monthly_rental_income="0",
        )
        data = json.loads(res)
        self.assertEqual(data['status'], 'created')
        holding_id = data['id']

        # 2. Query holdings
        holdings_res = mcp_srv.get_real_estate_holdings()
        holdings_list = json.loads(holdings_res)
        self.assertEqual(len(holdings_list), 1)
        self.assertEqual(holdings_list[0]['name'], "Jewar Airport Commercial Corridor")

        # 3. Query detail & prompt
        detail_res = json.loads(mcp_srv.get_real_estate_detail(holding_id=holding_id))
        self.assertEqual(detail_res['city'], 'Greater Noida')
        self.assertIn('llm_research_prompt', detail_res)

        prompt_str = mcp_srv.get_real_estate_llm_prompt(holding_id=holding_id)
        self.assertIn("Jewar Airport Commercial Corridor", prompt_str)

        # 4. Update valuation
        val_res = json.loads(mcp_srv.update_real_estate_valuation(
            holding_id=holding_id,
            current_valuation="25000000",
            notes="Recent airport flight trials boost corridor valuation",
        ))
        self.assertEqual(val_res['status'], 'updated')
        self.assertEqual(Decimal(val_res['current_valuation']), Decimal('25000000'))

        # 5. Reject unsafe javascript: URL in google_maps_url
        bad_url_res = mcp_srv.update_real_estate_holding(
            holding_id=holding_id,
            google_maps_url="javascript:alert(1)",
        )
        self.assertIn("Error", bad_url_res)

        # 6. Delete record via generic delete_record MCP tool
        del_res = json.loads(mcp_srv.delete_record(
            model_name="portfolio.RealEstateHolding",
            record_id=holding_id,
        ))
        self.assertEqual(del_res['status'], 'deleted')
        self.assertEqual(RealEstateHolding.objects.count(), 0)


class FinancialGoalRoadmapTests(TestCase):
    """FY-wise goals: closed years freeze on the March snapshot, open years track live value."""

    def setUp(self):
        from portfolio.models import CashPosition, FinancialGoal
        self.FinancialGoal = FinancialGoal
        self.group = AccountGroup.objects.create(name="Goal Family")
        CashPosition.objects.create(group=self.group, name="Bank", amount=Decimal("6000000"))
        self.today = datetime.date(2026, 10, 2)  # FY 2026-27, ~50% elapsed

    def _roadmap(self):
        from portfolio.services import build_goal_roadmap
        return build_goal_roadmap(self.group, Decimal("6000000"), today=self.today)

    def test_save_derives_fy_and_target_date(self):
        g = self.FinancialGoal.objects.create(group=self.group, label="A", target_amount=1, financial_year="FY 2027-28")
        self.assertEqual(g.target_date, datetime.date(2028, 3, 31))
        g2 = self.FinancialGoal.objects.create(group=self.group, label="B", target_amount=1, target_date=datetime.date(2026, 2, 1))
        self.assertEqual(g2.financial_year, "FY 2025-26")
        g3 = self.FinancialGoal.objects.create(group=self.group, label="C", target_amount=1, financial_year="Long Term")
        self.assertIsNone(g3.fy_start)
        self.assertIsNone(g3.target_date)

    def test_closed_year_uses_march_snapshot_not_live_value(self):
        MonthlySnapshot.objects.create(group=self.group, month=datetime.date(2026, 3, 1),
                                       total_current_value=Decimal("4000000"))
        self.FinancialGoal.objects.create(group=self.group, label="Missed", target_amount=5000000, financial_year="FY 2025-26")
        self.FinancialGoal.objects.create(group=self.group, label="Hit", target_amount=3500000, financial_year="FY 2025-26")
        rm = self._roadmap()
        closed = {g['label']: g for g in rm['goals'] if g['state'] == 'closed'}
        # Live value (60L) exceeds 50L but the FY closed at 40L → still missed.
        self.assertEqual(closed['Missed']['status'], 'missed')
        self.assertEqual(closed['Hit']['status'], 'achieved')
        self.assertEqual(rm['closed'][0]['verdict'], 'partial')
        self.assertIsNone(self.FinancialGoal.objects.get(label="Missed").achieved_at)

    def test_current_year_pace_from_fy_opening(self):
        MonthlySnapshot.objects.create(group=self.group, month=datetime.date(2026, 3, 1),
                                       total_current_value=Decimal("5000000"))
        self.FinancialGoal.objects.create(group=self.group, label="FY27", target_amount=8000000, financial_year="FY 2026-27")
        rm = self._roadmap()
        s = rm['spotlight']
        # 10L of the 30L climb done (33%) vs ~50% of the year gone → behind.
        self.assertAlmostEqual(s['fy_progress_pct'], 33.3, places=1)
        self.assertEqual(s['status'], 'behind')
        self.assertEqual(s['remaining'], 2000000.0)
        self.assertGreater(s['monthly_needed'], 0)

    def test_open_goal_stamps_achieved_at(self):
        g = self.FinancialGoal.objects.create(group=self.group, label="Next", target_amount=5000000, financial_year="FY 2027-28")
        rm = self._roadmap()
        self.assertEqual(rm['upcoming'][0]['goals'][0]['status'], 'achieved')
        g.refresh_from_db()
        self.assertEqual(g.achieved_at, self.today)

    def test_march_snapshot_locks_closing_value(self):
        g = self.FinancialGoal.objects.create(group=self.group, label="FY26", target_amount=1, financial_year="FY 2025-26")
        take_monthly_snapshot(month=datetime.date(2026, 3, 1), group=self.group)
        g.refresh_from_db()
        self.assertEqual(g.closing_value, Decimal("6000000"))

    def test_baby_summary_ignores_goals(self):
        g = self.FinancialGoal.objects.create(group=self.group, label="X", target_amount=1, financial_year="FY 2027-28")
        summary = get_portfolio_summary(self.group, is_baby=True)
        self.assertEqual(summary['goals'], [])
        g.refresh_from_db()
        self.assertIsNone(g.achieved_at)

    def test_form_rejects_bad_fy(self):
        from portfolio.forms import FinancialGoalForm
        form = FinancialGoalForm(data={'financial_year': 'FY26', 'label': 'x', 'target_amount': '1'})
        self.assertFalse(form.is_valid())
        self.assertIn('financial_year', form.errors)


class EmailRenderingTests(TestCase):
    """Scheduled emails render with and without data and use the previous month's snapshot."""

    def setUp(self):
        from portfolio.models import CashPosition
        self.group = AccountGroup.objects.create(name="Mail Family")
        CashPosition.objects.create(group=self.group, name="Bank", amount=Decimal("700000"))

    def test_inr_filters(self):
        from portfolio.templatetags.indian_format import inr, inr_short
        self.assertEqual(inr(Decimal("12079850.4")), "₹1,20,79,850")
        self.assertEqual(inr(-1500), "−₹1,500")
        self.assertEqual(inr_short(12400000), "₹1.24 Cr")
        self.assertEqual(inr_short(850000), "₹8.5 L")
        self.assertEqual(inr_short(-42000), "−₹42K")

    def test_monthly_renders_without_insights_or_snapshots(self):
        from django.template.loader import render_to_string
        from portfolio.emails import build_monthly_context
        ctx = build_monthly_context(self.group, None)
        self.assertIsNone(ctx['since'])
        html = render_to_string('emails/monthly_summary.html', ctx)
        self.assertIn('₹7,00,000', html)
        self.assertIn('No AI review this month', html)

    def test_monthly_compares_against_previous_month_snapshot(self):
        from django.utils import timezone
        from portfolio.emails import build_monthly_context
        this_month = timezone.localdate().replace(day=1)
        prev = (this_month - datetime.timedelta(days=1)).replace(day=1)
        MonthlySnapshot.objects.create(group=self.group, month=prev,
                                       total_current_value=Decimal("600000"), total_invested=Decimal("650000"))
        MonthlySnapshot.objects.create(group=self.group, month=this_month,
                                       total_current_value=Decimal("700000"), total_invested=Decimal("700000"))
        since = build_monthly_context(self.group, {'score': 80, 'insights': []})['since']
        self.assertEqual(since['month'], prev)
        self.assertEqual(since['change'], Decimal("100000"))
        self.assertEqual(since['money_added'], Decimal("50000"))
        self.assertEqual(since['market'], Decimal("50000"))

    def test_weekly_floor_and_render(self):
        from django.template.loader import render_to_string
        from portfolio.models import FixedDeposit
        from portfolio.emails import apply_floor, build_weekly_context
        FixedDeposit.objects.create(
            group=self.group, name="HDFC 1Y", account_name="Primary Acc",
            principal=Decimal("200000"), interest_rate=Decimal("7.0"),
            start_date=datetime.date.today(), maturity_date=datetime.date.today() + datetime.timedelta(days=365),
            is_active=True,
        )
        ctx = apply_floor(build_weekly_context(self.group), 1000000.0)
        self.assertEqual(ctx['deficit'], 100000.0)
        self.assertEqual(ctx['coverage_pct'], 90)
        self.assertEqual(len(ctx['cash_positions']), 1)
        self.assertEqual(len(ctx['fds']), 1)
        html = render_to_string('emails/weekly_brief.html', ctx)
        self.assertIn('Hold &amp; rebuild', html)
        self.assertIn('Where reserves sit', html)
        self.assertIn('Bank', html)
        self.assertIn('HDFC 1Y', html)
        self.assertIn('Primary Acc', html)
        self.assertNotIn('<details', html)


class FyEndAutomationTests(TestCase):
    """1 April jobs: land appreciation (once per FY) and the FY review email."""

    def setUp(self):
        self.group = AccountGroup.objects.create(name="FY Family")
        base = dict(group=self.group, area_value=Decimal("200"), locality="Sector 1",
                    purchase_date=datetime.date(2020, 1, 1), purchase_price=Decimal("1000000"))
        self.plot = RealEstateHolding.objects.create(name="Plot", property_type="PLOT_LAND",
                                                     current_valuation=Decimal("1000000"), **base)
        self.flat = RealEstateHolding.objects.create(name="Flat", property_type="APARTMENT_FLAT",
                                                     current_valuation=Decimal("5000000"), **base)
        self.apr1 = datetime.date(2026, 4, 1)

    def test_land_appreciates_once_per_fy_and_skips_buildings(self):
        from portfolio.services import apply_annual_land_appreciation
        fy, results = apply_annual_land_appreciation(today=self.apr1)
        self.assertEqual(fy, "FY 2025-26")
        self.assertEqual([r['holding'].name for r in results], ["Plot"])
        self.plot.refresh_from_db()
        self.flat.refresh_from_db()
        self.assertEqual(self.plot.current_valuation, Decimal("1060000"))
        self.assertEqual(self.plot.last_valuation_date, self.apr1)
        self.assertEqual(self.flat.current_valuation, Decimal("5000000"))
        _, again = apply_annual_land_appreciation(today=self.apr1 + datetime.timedelta(days=3))
        self.assertEqual(again, [])
        self.plot.refresh_from_db()
        self.assertEqual(self.plot.current_valuation, Decimal("1060000"))

    def test_recent_manual_revaluation_is_not_marked_up(self):
        from portfolio.services import apply_annual_land_appreciation
        self.plot.last_valuation_date = datetime.date(2026, 3, 20)
        self.plot.save()
        _, results = apply_annual_land_appreciation(today=self.apr1)
        self.assertTrue(results[0]['skipped'])
        self.plot.refresh_from_db()
        self.assertEqual(self.plot.current_valuation, Decimal("1000000"))
        self.assertEqual(self.plot.last_appreciated_fy, "FY 2025-26")

    def test_fy_review_verdict_and_next_year(self):
        from django.template.loader import render_to_string
        from portfolio.emails import build_fy_review_context
        from portfolio.models import FinancialGoal
        MonthlySnapshot.objects.create(group=self.group, month=datetime.date(2025, 3, 1),
                                       total_current_value=Decimal("5000000"), total_invested=Decimal("4000000"))
        MonthlySnapshot.objects.create(group=self.group, month=datetime.date(2026, 3, 1),
                                       total_current_value=Decimal("6200000"), total_invested=Decimal("4500000"))
        FinancialGoal.objects.create(group=self.group, label="Hit", target_amount=6000000, financial_year="FY 2025-26")
        FinancialGoal.objects.create(group=self.group, label="Stretch", target_amount=7000000, financial_year="FY 2025-26")
        FinancialGoal.objects.create(group=self.group, label="Next", target_amount=7400000, financial_year="FY 2026-27")

        ctx = build_fy_review_context(self.group, 2025)
        self.assertEqual(ctx['verdict'], 'partial')
        self.assertEqual(ctx['goals_hit'], 1)
        self.assertEqual(ctx['year']['money_added'], Decimal("500000"))
        self.assertEqual(ctx['year']['market'], Decimal("700000"))
        self.assertEqual(ctx['next_goals'][0]['gap'], Decimal("1200000"))
        self.assertEqual(ctx['next_goals'][0]['monthly'], Decimal("100000"))
        html = render_to_string('emails/fy_review.html', ctx)
        self.assertIn('You hit 1 of 2 targets in FY 2025-26', html)


class WebAuthnFlowTests(TestCase):
    """Biometric unlock: CSRF on the setup prompt, single-use expiring challenges, per-user credentials."""

    def setUp(self):
        from tracker.models import WebAuthnCredential
        self.group = AccountGroup.objects.create(name="Home")
        self.group.set_portfolio_password("pass123")
        self.group.save()
        self.user = User.objects.create_user(username="me", password="pw", user_type="PRIMARY", group=self.group)
        self.spouse = User.objects.create_user(username="sp", password="pw", user_type="ACCOUNT_HOLDER", group=self.group)
        self.other_cred = WebAuthnCredential.objects.create(user=self.spouse, credential_id=b'spouse-cred', public_key=b'pk')
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)

    def _csrf(self, resp):
        import re
        m = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', resp.content)
        self.assertIsNotNone(m, "page must carry a CSRF token (CSRF cookie is HttpOnly)")
        return m.group(1).decode()

    def _password_unlock(self):
        page = self.client.get('/portfolio/unlock/')
        return self.client.post('/portfolio/unlock/', {'password': 'pass123', 'csrfmiddlewaretoken': self._csrf(page)})

    def _post(self, name, token, body=None):
        return self.client.post(reverse(name), data=json.dumps(body or {}), content_type='application/json',
                                HTTP_X_CSRFTOKEN=token)

    def test_setup_prompt_after_password_unlock_can_start_registration(self):
        resp = self._password_unlock()
        self.assertContains(resp, 'registerBiometricBtn')
        begin = self._post('webauthn_register_begin', self._csrf(resp))
        self.assertEqual(begin.status_code, 200)
        self.assertIn('challenge', begin.json())

    def test_register_begin_requires_unlocked_vault(self):
        page = self.client.get('/portfolio/unlock/')
        self.assertEqual(self._post('webauthn_register_begin', self._csrf(page)).status_code, 403)

    def test_auth_complete_unlocks_and_challenge_is_single_use(self):
        from unittest import mock
        from tracker.models import WebAuthnCredential
        WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        token = self._csrf(self.client.get('/portfolio/unlock/'))
        self.assertEqual(self._post('webauthn_auth_begin', token).status_code, 200)
        body = {'rawId': 'bXktY3JlZA', 'id': 'bXktY3JlZA'}  # base64url(b'my-cred')
        with mock.patch('webauthn.verify_authentication_response', return_value=mock.Mock(new_sign_count=3)):
            self.assertEqual(self._post('webauthn_auth_complete', token, body).status_code, 200)
            self.assertIn('portfolio_unlocked_at', self.client.session)
            self.assertEqual(self._post('webauthn_auth_complete', token, body).status_code, 400)

    def test_expired_challenge_is_rejected(self):
        from unittest import mock
        from tracker.models import WebAuthnCredential
        WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        token = self._csrf(self.client.get('/portfolio/unlock/'))
        self._post('webauthn_auth_begin', token)
        s = self.client.session
        s['webauthn_auth_challenge']['t'] -= 3600
        s.save()
        with mock.patch('webauthn.verify_authentication_response', return_value=mock.Mock(new_sign_count=3)):
            resp = self._post('webauthn_auth_complete', token, {'rawId': 'bXktY3JlZA'})
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn('portfolio_unlocked_at', self.client.session)

    def test_cannot_use_another_users_credential(self):
        from unittest import mock
        from tracker.models import WebAuthnCredential
        WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        token = self._csrf(self.client.get('/portfolio/unlock/'))
        self._post('webauthn_auth_begin', token)
        with mock.patch('webauthn.verify_authentication_response', return_value=mock.Mock(new_sign_count=1)):
            resp = self._post('webauthn_auth_complete', token, {'rawId': 'c3BvdXNlLWNyZWQ'})  # b'spouse-cred'
        self.assertEqual(resp.status_code, 400)

    def test_malformed_auth_body_is_400_not_500(self):
        from tracker.models import WebAuthnCredential
        WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        token = self._csrf(self.client.get('/portfolio/unlock/'))
        self._post('webauthn_auth_begin', token)
        resp = self.client.post(reverse('webauthn_auth_complete'), data='not json', content_type='application/json',
                                HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 400)

    def test_account_holder_can_remove_own_device_only(self):
        from tracker.models import WebAuthnCredential
        mine = WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        c = Client()
        c.force_login(self.spouse)
        s = c.session
        s['portfolio_unlocked_at'] = time.time()
        s.save()
        c.post(reverse('webauthn_remove'), data=json.dumps({'id': mine.pk}), content_type='application/json')
        self.assertTrue(WebAuthnCredential.objects.filter(pk=mine.pk).exists())
        resp = c.post(reverse('webauthn_remove'), data=json.dumps({'id': self.other_cred.pk}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(WebAuthnCredential.objects.filter(pk=self.other_cred.pk).exists())

    def test_biometric_still_offered_during_password_lockout(self):
        from tracker.models import WebAuthnCredential
        WebAuthnCredential.objects.create(user=self.user, credential_id=b'my-cred', public_key=b'pk')
        s = self.client.session
        s['_portfolio_unlock_lockout'] = time.time() + 300
        s.save()
        self.assertContains(self.client.get('/portfolio/unlock/'), 'biometricBtn')


class ExcludeRealEstateToggleTests(TestCase):
    def setUp(self):
        from portfolio.models import CashPosition
        self.group = AccountGroup.objects.create(name="Home")
        self.user = User.objects.create_user(username="me", password="pw", user_type="PRIMARY", group=self.group)
        RealEstateHolding.objects.create(
            group=self.group, name="Plot", property_type="PLOT_LAND", area_value=Decimal("200"), area_unit="GAJ",
            purchase_price=Decimal("4000000"), current_valuation=Decimal("6000000"),
            purchase_date=datetime.date(2020, 1, 1))
        CashPosition.objects.create(group=self.group, name="Bank", amount=Decimal("1000000"))
        self.client.force_login(self.user)
        s = self.client.session
        s['portfolio_unlocked_at'] = time.time()
        s.save()

    def test_toggle_rebases_totals_and_persists(self):
        # Default is exclude_re = True (Include real estate toggle OFF by default)
        default_resp = self.client.get('/portfolio/')
        self.assertContains(default_resp, 'Include real estate')
        self.assertTrue(default_resp.context['exclude_re'])
        self.assertEqual(default_resp.context['total_value'], Decimal("1000000"))
        self.assertNotIn('Real Estate', [a['name'] for a in default_resp.context['assets']])
        self.assertContains(default_resp, 'excl. Real Estate')

        # User turns ON real estate (ex_re=0)
        inc = self.client.get('/portfolio/?ex_re=0')
        ctx_inc = inc.context
        self.assertFalse(ctx_inc['exclude_re'])
        self.assertEqual(ctx_inc['total_value'], Decimal("7000000"))
        self.assertEqual(ctx_inc['total_invested'], Decimal("5000000"))
        self.assertIn('Real Estate', [a['name'] for a in ctx_inc['assets']])
        self.assertIn('Real Estate', [c['name'] for c in ctx_inc['consolidated']])

        # User turns OFF real estate (ex_re=1)
        ex = self.client.get('/portfolio/?ex_re=1')
        ctx = ex.context
        self.assertTrue(ctx['exclude_re'])
        self.assertEqual(ctx['total_value'], Decimal("1000000"))
        self.assertEqual(ctx['total_invested'], Decimal("1000000"))
        self.assertNotIn('Real Estate', [a['name'] for a in ctx['assets']])
        self.assertNotIn('Real Estate', [c['name'] for c in ctx['consolidated']])
        self.assertNotIn('Real Estate', ctx['pf_chart_data']['labels'])
        self.assertContains(ex, 'excl. Real Estate')

        # Session persistence
        self.assertTrue(self.client.get('/portfolio/').context['exclude_re'])
        self.assertFalse(self.client.get('/portfolio/?ex_re=0').context['exclude_re'])

    def test_toggle_rebases_goals_roadmap(self):
        from portfolio.models import FinancialGoal
        from portfolio.services import fy_start_year
        today = datetime.date.today()
        cur_fy = fy_start_year(today)
        goal = FinancialGoal.objects.create(
            group=self.group,
            label="Reach 50L",
            target_amount=Decimal("5000000"),
            financial_year=f"FY {cur_fy}-{str(cur_fy + 1)[-2:]}",
        )

        # 1. By default, real estate is excluded (non-RE = 10L < 50L) -> Goal NOT achieved
        default_resp = self.client.get('/portfolio/')
        rm_default = default_resp.context['goal_roadmap']
        self.assertIsNotNone(rm_default)
        goal_item = next(g for g in rm_default['goals'] if g['id'] == goal.id)
        self.assertFalse(goal_item['achieved'])
        self.assertEqual(goal_item['remaining'], 4000000.0)
        self.assertContains(default_resp, 'excl. Real Estate')

        # 2. When real estate is included (total = 70L >= 50L) -> Goal achieved
        inc_resp = self.client.get('/portfolio/?ex_re=0')
        rm_inc = inc_resp.context['goal_roadmap']
        goal_item_inc = next(g for g in rm_inc['goals'] if g['id'] == goal.id)
        self.assertTrue(goal_item_inc['achieved'])
        self.assertEqual(goal_item_inc['surplus'], 2000000.0)

        # 3. Switching back to excluded: DB record is not corrupted
        ex_resp = self.client.get('/portfolio/?ex_re=1')
        rm_ex = ex_resp.context['goal_roadmap']
        goal_item_ex = next(g for g in rm_ex['goals'] if g['id'] == goal.id)
        self.assertFalse(goal_item_ex['achieved'])
        self.assertEqual(goal_item_ex['remaining'], 4000000.0)

    def test_fy_performance_excludes_real_estate_only_when_snapshot_has_breakdown(self):
        from portfolio.services import get_fy_performance
        today = datetime.date(2026, 10, 1)
        snap = MonthlySnapshot.objects.create(
            group=self.group, month=datetime.date(2026, 3, 1),
            total_current_value=Decimal("6500000"), total_invested=Decimal("4800000"), total_returns=Decimal("1700000"),
            data={'real_estate': {'current': 5500000.0, 'invested': 4000000.0}})
        perf = get_fy_performance(self.group, Decimal("1100000"), Decimal("900000"), today=today, exclude_real_estate=True)
        self.assertEqual(perf['opening_value'], Decimal("1000000"))
        self.assertEqual(perf['change'], Decimal("100000"))
        self.assertEqual(perf['money_added'], Decimal("100000"))

        snap.data = {}
        snap.save()
        self.assertIsNone(get_fy_performance(self.group, Decimal("1100000"), Decimal("900000"),
                                             today=today, exclude_real_estate=True))


class ShaktiCloudIntegrationTests(TestCase):
    def test_clean_json_text_strips_think_tags_and_fences(self):
        from portfolio.ai import _clean_json_text

        raw = (
            "<think>Analyzing 6 pillars: Diversification is good, score 74.</think>\n"
            "```json\n"
            '{"summary": "Solid portfolio.", "score": 74, "insights": [], "market_context": "Bullish", "outlook": "Hold"}\n'
            "```"
        )
        cleaned = _clean_json_text(raw)
        self.assertNotIn("<think>", cleaned)
        self.assertNotIn("```", cleaned)
        data = json.loads(cleaned)
        self.assertEqual(data["score"], 74)
        self.assertEqual(data["summary"], "Solid portfolio.")

    def test_schema_normalizes_casing_and_synonyms(self):
        from portfolio.ai import PortfolioInsightsResponse

        payload = {
            "summary": "Diversified household wealth.",
            "score": "82/100",  # String with formatting
            "insights": [
                {
                    "category": "ASSET_ALLOCATION",  # synonym in uppercase
                    "severity": "CRITICAL",          # uppercase
                    "title": "High Equity Exposure",
                    "detail": "Equity accounts for 75% of liquid portfolio.",
                    "action": "Trim 5% into liquid debt.",
                },
                {
                    "category": "risk",
                    "severity": "good",              # synonym for positive
                    "title": "Zero Debt",
                    "detail": "Emergency fund is intact.",
                }
            ],
            "market_context": "Nifty trading at 22x P/E",
            "outlook": "Maintain monthly SIPs."
        }
        validated = PortfolioInsightsResponse.model_validate(payload)
        self.assertEqual(validated.score, 82)
        self.assertEqual(validated.insights[0].category.value, "rebalancing")
        self.assertEqual(validated.insights[0].severity.value, "critical")
        self.assertEqual(validated.insights[1].severity.value, "positive")

    def test_call_shakti_mocked_success(self):
        from unittest.mock import patch, MagicMock
        from portfolio.ai import call_shakti

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content='{"summary": "Mock summary", "score": 78, "insights": [], "market_context": "Neutral", "outlook": "Steady"}'))]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = [mock_chunk]

        with patch("openai.OpenAI", return_value=mock_client), \
             patch.dict("os.environ", {"SHAKTI_API_KEY": "mock-shakti-key", "SHAKTI_MODEL": "llama3_3"}):
            res = call_shakti({"summary": {"total_value": 1000000}})
            self.assertEqual(res.model, "shakti:llama3_3")
            self.assertEqual(res.insights_dict["score"], 78)
            self.assertEqual(res.insights_dict["summary"], "Mock summary")
            # Verify client was initialized with Shakti default headers
            mock_client.chat.completions.create.assert_called_once()


class PortfolioInsightsDAGTests(TestCase):
    def test_intermediate_schemas_validation(self):
        from portfolio.dag import (
            AllocationLensResult,
            QualityLensResult,
            MacroStressLensResult,
            StrategyLensResult,
            DAGExecutionMetadata,
        )

        alloc = AllocationLensResult(
            sub_score=85,
            allocation_findings=["75% Equity, 25% Debt"],
            concentration_warnings=["HDFC Bank is 12%"],
            liquidity_tier_assessment="Tier 1 exceeds 6 months",
            emergency_floor_ok=True,
        )
        self.assertEqual(alloc.sub_score, 85)
        self.assertTrue(alloc.emergency_floor_ok)

        qual = QualityLensResult(
            sub_score=75,
            equity_quality_findings=["Top gainer: Tata Motors"],
            legacy_fund_audits=[{"fund_name": "Axis Bluechip", "action": "merge", "target": "Nifty 50 Index"}],
        )
        self.assertEqual(qual.sub_score, 75)
        self.assertEqual(len(qual.legacy_fund_audits), 1)

        macro = MacroStressLensResult(
            sub_score=70,
            valuation_regime="Nifty PE 21.5 (Fair)",
            crash_drawdown_amount="Rs 12.5L",
        )
        self.assertEqual(macro.sub_score, 70)

        strat = StrategyLensResult(
            sub_score=80,
            tax_harvesting_plan="Harvest 1.25L LTCG",
        )
        self.assertEqual(strat.sub_score, 80)

        meta = DAGExecutionMetadata(
            started_at="2026-10-13T10:00:00Z",
            completed_at="2026-10-13T10:00:02Z",
            elapsed_ms=2000.0,
            nodes_executed=["Stage1A", "Stage1B", "Stage1C", "Stage2", "Stage3"],
            sub_scores={"allocation": 85, "quality": 75, "strategy": 80, "macro": 70},
            grounded_score=78,
            fallback_used=False,
        )
        self.assertEqual(meta.grounded_score, 78)
        self.assertFalse(meta.fallback_used)

    def test_terminal_grounded_score_formula(self):
        from portfolio.dag import (
            AllocationLensResult,
            QualityLensResult,
            MacroStressLensResult,
            StrategyLensResult,
            run_stage_3_terminal_synthesis,
        )
        from portfolio.ai import PortfolioInsightsResponse
        from unittest.mock import patch

        alloc = AllocationLensResult(sub_score=80)
        qual = QualityLensResult(sub_score=70)
        strat = StrategyLensResult(sub_score=90)
        macro = MacroStressLensResult(sub_score=60)
        # Expected grounded score: round(0.30*80 + 0.25*70 + 0.25*90 + 0.20*60)
        # = 24 + 17.5 + 22.5 + 12 = 76

        mock_llm_response = PortfolioInsightsResponse(
            summary="Strong foundation with actionable rebalancing.",
            score=99,  # LLM attempted to hallucinate 99
            insights=[],
            market_context="Neutral",
            outlook="Maintain SIPs",
        )

        with patch("portfolio.dag.gateway.generate_structured", return_value=mock_llm_response):
            synth = run_stage_3_terminal_synthesis(
                data={"summary": {"total_value": 1000000}},
                investor_profile="Profile test",
                allocation=alloc,
                quality=qual,
                macro=macro,
                strategy=strat,
            )
            # Must strictly overwrite hallucinated score 99 with mathematically grounded score 76
            self.assertEqual(synth.score, 76)

    def test_dag_execution_with_mocked_gateway(self):
        from portfolio.dag import (
            PortfolioInsightsDAG,
            AllocationLensResult,
            QualityLensResult,
            MacroStressLensResult,
            StrategyLensResult,
        )
        from portfolio.ai import PortfolioInsightsResponse, Insight
        from unittest.mock import patch

        def mock_generate_structured(schema, *args, **kwargs):
            if schema == AllocationLensResult:
                return AllocationLensResult(
                    sub_score=82,
                    allocation_findings=["Balanced 70:30"],
                    candidate_insights=[
                        Insight(category="rebalancing", severity="info", title="Rebalance equity", detail="Equity is 72%")
                    ],
                )
            elif schema == QualityLensResult:
                return QualityLensResult(
                    sub_score=78,
                    legacy_fund_audits=[{"fund_name": "Old Fund", "action": "exit"}],
                )
            elif schema == MacroStressLensResult:
                return MacroStressLensResult(
                    sub_score=74,
                    valuation_regime="Fair value",
                )
            elif schema == StrategyLensResult:
                return StrategyLensResult(
                    sub_score=80,
                    tax_harvesting_plan="Utilize 1.25L LTCG",
                )
            elif schema == PortfolioInsightsResponse:
                return PortfolioInsightsResponse(
                    summary="Solid asset mix with high equity discipline.",
                    score=65,  # will be overridden by grounded formula
                    insights=[
                        Insight(category="rebalancing", severity="info", title="Rebalance equity", detail="Equity is 72%")
                    ],
                )
            raise ValueError(f"Unknown schema: {schema}")

        with patch("portfolio.dag.gateway.generate_structured", side_effect=mock_generate_structured):
            dag = PortfolioInsightsDAG(use_concurrent=True)
            res, meta = dag.execute({"summary": {"total_value": 5000000}})

            self.assertEqual(len(meta.nodes_executed), 5)
            self.assertFalse(meta.fallback_used)
            # 0.30*82 + 0.25*78 + 0.25*80 + 0.20*74 = 24.6 + 19.5 + 20 + 14.8 = 78.9 -> 79
            self.assertEqual(res.score, 79)
            self.assertEqual(meta.grounded_score, 79)

    def test_dag_node_failure_resilience(self):
        from portfolio.dag import (
            PortfolioInsightsDAG,
            QualityLensResult,
            MacroStressLensResult,
            StrategyLensResult,
        )
        from portfolio.ai import PortfolioInsightsResponse
        from unittest.mock import patch

        def mock_generate_with_fail(schema, *args, **kwargs):
            from portfolio.dag import AllocationLensResult
            if schema == AllocationLensResult:
                raise RuntimeError("Node 1A network timeout")
            elif schema == QualityLensResult:
                return QualityLensResult(sub_score=70)
            elif schema == MacroStressLensResult:
                return MacroStressLensResult(sub_score=65)
            elif schema == StrategyLensResult:
                return StrategyLensResult(sub_score=72)
            elif schema == PortfolioInsightsResponse:
                return PortfolioInsightsResponse(
                    summary="Resilient synthesis summary.",
                    score=70,
                    insights=[],
                )
            raise ValueError(f"Unknown schema: {schema}")

        with patch("portfolio.dag.gateway.generate_structured", side_effect=mock_generate_with_fail):
            dag = PortfolioInsightsDAG(use_concurrent=False)
            res, meta = dag.execute({"summary": {"total_value": 3000000}})

            # Fallback was utilized for Stage 1A, execution completed smoothly
            self.assertTrue(meta.fallback_used)
            self.assertEqual(res.summary, "Resilient synthesis summary.")
            self.assertGreater(res.score, 0)

    def test_dag_execute_async(self):
        import asyncio
        from portfolio.dag import (
            PortfolioInsightsDAG,
            AllocationLensResult,
            QualityLensResult,
            MacroStressLensResult,
            StrategyLensResult,
            arun_portfolio_insights_dag,
        )
        from portfolio.ai import PortfolioInsightsResponse
        from unittest.mock import patch

        def mock_generate(schema, *args, **kwargs):
            if schema == AllocationLensResult:
                return AllocationLensResult(sub_score=80)
            elif schema == QualityLensResult:
                return QualityLensResult(sub_score=75)
            elif schema == MacroStressLensResult:
                return MacroStressLensResult(sub_score=70)
            elif schema == StrategyLensResult:
                return StrategyLensResult(sub_score=85)
            elif schema == PortfolioInsightsResponse:
                return PortfolioInsightsResponse(
                    summary="Async DAG synthesis summary.",
                    score=78,
                    insights=[],
                )
            raise ValueError(f"Unknown schema: {schema}")

        with patch("portfolio.dag.gateway.generate_structured", side_effect=mock_generate):
            dag = PortfolioInsightsDAG()
            res, meta = asyncio.run(dag.execute_async({"summary": {"total_value": 3000000}}))
            self.assertEqual(res.summary, "Async DAG synthesis summary.")
            self.assertEqual(meta.grounded_score, 78)

            ai_res = asyncio.run(arun_portfolio_insights_dag({"summary": {"total_value": 3000000}}))
            self.assertEqual(ai_res.model, "vault-dag:multi-stage-async")
            self.assertIn("_dag_metadata", ai_res.insights_dict)


class PortfolioQueryOptimizationsTests(TestCase):
    def setUp(self):
        from tracker.models import AccountGroup
        from portfolio.models import ZerodhaAccount, StockHolding, MutualFundHolding, CommodityHolding, CommodityPrice
        self.group = AccountGroup.objects.create(name="Opt Group")
        self.account = ZerodhaAccount.objects.create(name="Z1", slug="z1", group=self.group)
        StockHolding.objects.create(
            account=self.account, symbol="INFY", quantity=10,
            purchase_value=Decimal('15000.00'), current_value=Decimal('18000.00')
        )
        MutualFundHolding.objects.create(
            account=self.account, fund_name="Nifty Index", fund_type="INDEX",
            units=Decimal('100.000'), purchase_value=Decimal('20000.00'), current_value=Decimal('25000.00')
        )
        MutualFundHolding.objects.create(
            account=self.account, fund_name="Flexi Cap", fund_type="OTHER",
            units=Decimal('50.000'), purchase_value=Decimal('10000.00'), current_value=Decimal('12000.00')
        )
        CommodityPrice.objects.create(commodity_type="GOLD", rate_per_gram=Decimal('7000.00'))
        CommodityHolding.objects.create(
            group=self.group, commodity_type="GOLD", description="Gold Bar",
            weight_grams=Decimal('10.00'), purchase_price_per_gram=Decimal('6000.00')
        )

    def test_zerodha_account_sums_aggregation(self):
        from portfolio.services import _zerodha_account_sums
        sums = _zerodha_account_sums([self.account])
        self.assertIn(self.account.id, sums)
        acct_sum = sums[self.account.id]
        self.assertEqual(acct_sum['stocks_cur'], Decimal('18000.00'))
        self.assertEqual(acct_sum['stocks_inv'], Decimal('15000.00'))
        self.assertEqual(acct_sum['index_cur'], Decimal('25000.00'))
        self.assertEqual(acct_sum['index_inv'], Decimal('20000.00'))
        self.assertEqual(acct_sum['other_cur'], Decimal('12000.00'))
        self.assertEqual(acct_sum['other_inv'], Decimal('10000.00'))

    def test_commodity_summary_aggregation(self):
        from portfolio.services import get_commodity_summary
        comm = get_commodity_summary(self.group)
        self.assertEqual(comm['gold_weight'], Decimal('10.00'))
        self.assertEqual(comm['gold_value'], Decimal('70000.00'))
        self.assertEqual(comm['commodity_invested'], Decimal('60000.00'))
        self.assertEqual(comm['commodity_returns'], Decimal('10000.00'))

    def test_portfolio_summary_aggregation(self):
        from portfolio.services import get_portfolio_summary
        summary = get_portfolio_summary(self.group)
        self.assertEqual(summary['total_value'], Decimal('125000.00'))
        self.assertEqual(summary['total_invested'], Decimal('105000.00'))
        self.assertEqual(summary['equity_total'], Decimal('55000.00'))
        self.assertEqual(summary['equity_invested'], Decimal('45000.00'))


class PFEntryTests(TestCase):
    """Tests for PF (Provident Fund / PPF) per-family-member accounts across UI, Services, and MCP."""

    def setUp(self):
        self.group = AccountGroup.objects.create(name="PF Household")
        self.group.set_portfolio_password("pass123")
        self.group.save()

        self.user = User.objects.create_user(
            username="atul",
            first_name="Atul",
            password="securepassword",
            user_type="PRIMARY",
            group=self.group,
        )
        self.client = Client()
        self.client.login(username="atul", password="securepassword")
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

    def test_pf_ui_and_summary_per_member(self):
        from portfolio.models import PFEntry

        # Add PF entry for Atul via UI
        resp = self.client.post(reverse('save_pf_fy_entry'), {
            'account_name': 'Atul',
            'fy_year': '2026',
            'contribution': '150000.00',
            'interest': '25000.00',
            'remarks': 'FY27 PPF Deposit',
        })
        self.assertEqual(resp.status_code, 302)

        # Add PF for Kanika
        PFEntry.objects.create(
            group=self.group,
            account_name='Kanika',
            fy_year=2026,
            financial_year='FY 2026-27',
            date=datetime.date(2026, 4, 10),
            contribution=Decimal('150000.00'),
            interest=Decimal('0.00'),
            remarks='Kanika PPF',
        )

        summary = get_portfolio_summary(self.group)
        self.assertEqual(summary['pf_total_contrib'], Decimal('300000.00'))
        self.assertEqual(summary['pf_total_interest'], Decimal('25000.00'))
        self.assertEqual(summary['pf_balance'], Decimal('325000.00'))
        self.assertEqual(len(summary['pf_accounts']), 2)
        self.assertEqual(summary['pf_accounts'][0]['account_name'], 'Atul')
        self.assertEqual(summary['pf_accounts'][0]['balance'], Decimal('175000.00'))
        self.assertEqual(summary['pf_accounts'][1]['account_name'], 'Kanika')
        self.assertEqual(summary['pf_accounts'][1]['balance'], Decimal('150000.00'))

        # Verify pf_detail page & member filter
        detail_resp = self.client.get(reverse('pf_detail'))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, 'Atul')
        self.assertContains(detail_resp, 'Kanika')

        kanika_resp = self.client.get(reverse('pf_detail') + '?member=Kanika')
        self.assertEqual(kanika_resp.status_code, 200)
        self.assertEqual(len(kanika_resp.context['entries']), 1)
        self.assertEqual(kanika_resp.context['balance'], Decimal('150000.00'))

        # Verify snapshot includes PF breakdown
        snap, _ = take_monthly_snapshot(datetime.date(2026, 4, 1), group=self.group)
        self.assertIn('pf', snap.data)
        self.assertEqual(snap.data['pf']['current'], 325000.0)
        self.assertEqual(len(snap.data['pf']['accounts']), 2)

    def test_pf_mcp_tools(self):
        # Create via MCP add_pf_entry
        res_str = mcp_srv.add_pf_entry(
            account_name="Kanika",
            date="2026-05-01",
            amount="100000",
            entry_type="CONTRIBUTION",
            remarks="MCP deposit",
        )
        res = json.loads(res_str)
        self.assertEqual(res['status'], 'created')
        self.assertEqual(res['account_name'], 'Kanika')
        entry_id = res['id']

        # Update via MCP update_pf_entry
        upd_str = mcp_srv.update_pf_entry(
            entry_id=entry_id,
            amount="125000",
            remarks="Updated MCP deposit",
        )
        upd = json.loads(upd_str)
        self.assertEqual(upd['status'], 'updated')

        # Read via MCP get_pf_details
        details = json.loads(mcp_srv.get_pf_details(account_name="Kanika"))
        self.assertEqual(Decimal(details['balance']), Decimal('125000.00'))
        self.assertEqual(len(details['entries']), 1)

        # Delete via MCP delete_record
        del_res = json.loads(mcp_srv.delete_record('portfolio.PFEntry', entry_id))
        self.assertEqual(del_res['status'], 'deleted')

    def test_pf_fy_breakdown_and_crud(self):
        from portfolio.models import PFEntry
        from portfolio.services import get_pf_fy_breakdown

        # 1. Save FY 2024-25 for Atul via save_pf_fy_entry
        resp = self.client.post(reverse('save_pf_fy_entry'), {
            'account_name': 'Atul',
            'fy_year': '2024',
            'contribution': '150000.00',
            'interest': '79385.00',
            'remarks': 'FY25 Credit',
        })
        self.assertEqual(resp.status_code, 302)

        # Verify 1 entry created per member/FY
        entries_fy24 = list(PFEntry.objects.filter(group=self.group, account_name='Atul'))
        self.assertEqual(len(entries_fy24), 1)
        self.assertEqual(entries_fy24[0].contribution, Decimal('150000.00'))
        self.assertEqual(entries_fy24[0].interest, Decimal('79385.00'))
        self.assertEqual(entries_fy24[0].date, datetime.date(2024, 4, 1))

        # 2. Save FY 2025-26 for Atul
        resp = self.client.post(reverse('save_pf_fy_entry'), {
            'account_name': 'Atul',
            'fy_year': '2025',
            'contribution': '100000.00',
            'interest': '91825.00',
            'remarks': 'FY26 Credit',
        })
        self.assertEqual(resp.status_code, 302)

        # 3. Test get_pf_fy_breakdown calculation
        breakdown = get_pf_fy_breakdown(self.group, selected_member='Atul')
        self.assertEqual(len(breakdown), 2)

        # Latest FY is first: FY 2025-26
        fy25 = breakdown[0]
        self.assertEqual(fy25['fy_year'], 2025)
        self.assertEqual(fy25['opening_balance'], Decimal('229385.00'))
        self.assertEqual(fy25['contribution'], Decimal('100000.00'))
        self.assertEqual(fy25['interest'], Decimal('91825.00'))
        self.assertEqual(fy25['annual_addition'], Decimal('191825.00'))
        self.assertEqual(fy25['closing_balance'], Decimal('421210.00'))

        # Older FY: FY 2024-25
        fy24 = breakdown[1]
        self.assertEqual(fy24['fy_year'], 2024)
        self.assertEqual(fy24['opening_balance'], Decimal('0.00'))
        self.assertEqual(fy24['contribution'], Decimal('150000.00'))
        self.assertEqual(fy24['interest'], Decimal('79385.00'))
        self.assertEqual(fy24['closing_balance'], Decimal('229385.00'))

        # 4. Update FY 2025-26 (edit existing)
        resp = self.client.post(reverse('save_pf_fy_entry'), {
            'action_type': 'edit',
            'account_name': 'Atul',
            'orig_member': 'Atul',
            'fy_year': '2025',
            'orig_fy_year': '2025',
            'contribution': '110000.00',
            'interest': '95000.00',
            'remarks': 'Updated FY26',
        })
        self.assertEqual(resp.status_code, 302)

        # Still 2 total entries in DB (1 for FY24, 1 for FY25)
        self.assertEqual(PFEntry.objects.filter(group=self.group).count(), 2)
        upd_entry = PFEntry.objects.get(group=self.group, fy_year=2025)
        self.assertEqual(upd_entry.contribution, Decimal('110000.00'))
        self.assertEqual(upd_entry.remarks, 'Updated FY26')

        # 4a. Add a new entry to existing FY 2025-26 (action_type='add') -> must ACCUMULATE, not rewrite
        resp = self.client.post(reverse('save_pf_fy_entry'), {
            'action_type': 'add',
            'account_name': 'Atul',
            'fy_year': '2025',
            'contribution': '40000.00',
            'interest': '5000.00',
            'remarks': 'Additional deposit',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(PFEntry.objects.filter(group=self.group).count(), 2)
        acc_entry = PFEntry.objects.get(group=self.group, fy_year=2025)
        self.assertEqual(acc_entry.contribution, Decimal('150000.00'))
        self.assertEqual(acc_entry.interest, Decimal('100000.00'))
        self.assertIn('Updated FY26', acc_entry.remarks)
        self.assertIn('Additional deposit', acc_entry.remarks)

        # 4b. Verify safe_redirect blocks external malicious redirect
        from django.test import RequestFactory
        from pftracker.utils import safe_redirect
        factory = RequestFactory()
        bad_req = factory.post(reverse('save_pf_fy_entry'), {'next': 'https://evil.com/phish'})
        red = safe_redirect(bad_req, fallback='pf_detail')
        self.assertEqual(red.url, reverse('pf_detail'))

        # 5. Check pf_detail view context
        detail_resp = self.client.get(reverse('pf_detail') + '?member=Atul')
        self.assertEqual(detail_resp.status_code, 200)
        self.assertIn('fy_entries', detail_resp.context)
        self.assertIn('fy_options', detail_resp.context)
        self.assertEqual(len(detail_resp.context['fy_entries']), 2)

        # 6. Delete FY 2024-25 via delete_pf_fy_entry
        del_resp = self.client.post(reverse('delete_pf_fy_entry'), {
            'account_name': 'Atul',
            'fy_year': '2024',
        })
        self.assertEqual(del_resp.status_code, 302)
        self.assertEqual(PFEntry.objects.filter(group=self.group, fy_year=2024).count(), 0)
        self.assertEqual(PFEntry.objects.filter(group=self.group).count(), 1)


class WeeklyBriefCommandTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="WeeklyHome")
        self.user = User.objects.create_user(username="weekly_user", password="pw", user_type="PRIMARY", group=self.group, email="test@example.com")

    @mock.patch('portfolio.management.commands.send_weekly_brief.gateway.generate_structured')
    @mock.patch('portfolio.management.commands.send_weekly_brief.gateway.is_available', return_value=True)
    def test_weekly_brief_ai_model_and_thinking(self, mock_avail, mock_gen):
        from portfolio.management.commands.send_weekly_brief import Command, WeeklyAnalysisResponse, AIContextItem

        mock_gen.return_value = WeeklyAnalysisResponse(safety_floor_inr=500000.0, items=[AIContextItem(symbol="INFY", context="Solid moat")])
        cmd = Command()
        floor, notes = cmd._ai_context(self.group, [{'symbol': 'INFY', 'pnl_pct': 10.0}])
        self.assertEqual(floor, 500000.0)
        self.assertEqual(notes, {'INFY': 'Solid moat'})
        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        self.assertEqual(kwargs.get('model'), 'gemini-3.8-flash')
        self.assertEqual(kwargs.get('thinking_level'), 'HIGH')


class LandAppraisalTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="LandGroup")
        self.plot = RealEstateHolding.objects.create(
            group=self.group,
            name="Yamuna Expressway Sector 22D Plot",
            property_type="PLOT_LAND",
            area_value=Decimal("250"),
            area_unit="GAJ",
            locality="Sector 22D, Yamuna Expressway",
            city="Greater Noida",
            state="Uttar Pradesh",
            micro_market_tag="yamuna_expressway_sec22d",
            purchase_date=datetime.date(2021, 5, 10),
            purchase_price=Decimal("8000000"),
            current_valuation=Decimal("12000000"),
        )
        self.apr1 = datetime.date(2026, 4, 1)

    @mock.patch('portfolio.land_appraisal.synthesize_land_appreciation')
    @mock.patch('portfolio.land_appraisal.run_deepseek_auditor_review')
    @mock.patch('portfolio.land_appraisal.discover_land_market_comps')
    def test_run_land_appraisal_dag_end_to_end(self, mock_stage1, mock_stage2, mock_stage3):
        from portfolio.land_appraisal import (
            GroundedMarketComps,
            DeepSeekAuditorReview,
            LandAppraisalSynthesis,
            run_land_appraisal_dag,
        )

        mock_stage1.return_value = GroundedMarketComps(
            locality="Sector 22D",
            city="Greater Noida",
            median_portal_ask_per_sq_yd=65000.0,
            circle_rate_floor_per_sq_yd=35000.0,
            circle_rate_growth_pct=7.0,
            observed_market_growth_pct=8.5,
            rbi_repo_rate_pct=6.5,
            cpi_inflation_pct=5.4,
            infrastructure_delay_months=6,
            infrastructure_catalysts=["Noida International Airport", "Film City"],
            summary="Strong corridor momentum",
        )
        mock_stage2.return_value = DeepSeekAuditorReview(
            gross_market_growth_pct=8.5,
            speculative_ask_haircut_pct=30.0,
            illiquidity_friction_discount_pct=15.0,
            execution_slippage_penalty_pct=2.5,
            max_allowable_yoy_growth_cap_pct=14.9,
            conservative_appreciation_ceiling_pct=5.5,
            auditor_verdict="Deduct speculative asking premiums.",
            key_skeptical_concerns=["Possession delays"],
        )
        mock_stage3.return_value = LandAppraisalSynthesis(
            holding_id=self.plot.id,
            holding_name=self.plot.name,
            closing_fy="FY 2025-26",
            current_valuation_inr=12000000.0,
            recommended_appreciation_pct=5.5,
            new_valuation_inr=12660000.0,
            net_value_increase_inr=660000.0,
            implied_rate_per_sq_yd_inr=50640.0,
            conservative_margin_of_safety_pct=3.0,
            methodology_summary="Grounded at 5.5% net after fiduciary haircuts.",
            key_drivers=["Airport progress"],
            risk_haircuts_applied=["Speculative broker markup discount"],
            confidence_score=0.9,
            model_chain_used="gemini-grounding -> deepseek-auditor -> gemini-4-argon",
        )

        appraisal = run_land_appraisal_dag(self.plot, closing_fy="FY 2025-26", today=self.apr1, is_debug=False)
        self.assertEqual(appraisal.recommended_appreciation_pct, 5.5)
        self.assertEqual(appraisal.new_valuation_inr, 12660000.0)
        self.assertIn("gemini-4-argon", appraisal.model_chain_used)

    @mock.patch('portfolio.land_appraisal.run_land_appraisal_dag')
    def test_apply_annual_land_appreciation_with_ai(self, mock_dag):
        from portfolio.services import apply_annual_land_appreciation
        from portfolio.land_appraisal import LandAppraisalSynthesis

        mock_dag.return_value = LandAppraisalSynthesis(
            holding_id=self.plot.id,
            holding_name=self.plot.name,
            closing_fy="FY 2025-26",
            current_valuation_inr=12000000.0,
            recommended_appreciation_pct=6.5,
            new_valuation_inr=12780000.0,
            net_value_increase_inr=780000.0,
            implied_rate_per_sq_yd_inr=51120.0,
            conservative_margin_of_safety_pct=2.0,
            methodology_summary="Balanced FY appraisal via synthesized DAG",
            key_drivers=["Corridor expansion"],
            risk_haircuts_applied=["Illiquidity discount"],
            confidence_score=0.88,
            model_chain_used="gemini-grounding -> deepseek-auditor -> gemini-4-argon",
        )

        fy, results = apply_annual_land_appreciation(today=self.apr1, use_ai=True)
        self.assertEqual(fy, "FY 2025-26")
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r['pct'], Decimal('6.5'))
        self.assertEqual(r['new'], Decimal('12780000'))
        self.plot.refresh_from_db()
        self.assertEqual(self.plot.current_valuation, Decimal('12780000'))
        self.assertEqual(self.plot.last_appreciated_fy, "FY 2025-26")
        self.assertIn("[AI FY-End Appraisal FY 2025-26]", self.plot.remarks)

    def test_land_appraisal_dag_fallbacks(self):
        from portfolio.land_appraisal import (
            _fallback_market_comps,
            _fallback_auditor_review,
            _fallback_synthesis,
        )
        comps = _fallback_market_comps(self.plot)
        self.assertEqual(comps.observed_market_growth_pct, 7.5)
        auditor = _fallback_auditor_review(comps)
        self.assertEqual(auditor.conservative_appreciation_ceiling_pct, 6.0)
        synth = _fallback_synthesis(self.plot, "FY 2025-26", comps, auditor)
        self.assertEqual(synth.recommended_appreciation_pct, 6.0)
        self.assertEqual(synth.new_valuation_inr, 12720000.0)

    @mock.patch('portfolio.management.commands.appreciate_land.apply_annual_land_appreciation')
    def test_appreciate_land_command_options(self, mock_apply):
        from django.core.management import call_command
        from io import StringIO
        mock_apply.return_value = ("FY 2025-26", [{
            'holding': self.plot,
            'old': Decimal('12000000'),
            'new': Decimal('12720000'),
            'pct': Decimal('6.00'),
            'appraisal': None,
            'skipped': False,
        }])

        # 1. Test default AI mode
        out = StringIO()
        call_command('appreciate_land', stdout=out)
        mock_apply.assert_called_with(pct=None, dry_run=False, use_ai=True)

        # 2. Test --no-ai
        out = StringIO()
        call_command('appreciate_land', '--no-ai', stdout=out)
        mock_apply.assert_called_with(pct=None, dry_run=False, use_ai=False)

        # 3. Test manual --pct
        out = StringIO()
        call_command('appreciate_land', '--pct', '7.5', stdout=out)
        mock_apply.assert_called_with(pct=Decimal('7.5'), dry_run=False, use_ai=False)

        # 4. Test --dry-run
        out = StringIO()
        call_command('appreciate_land', '--dry-run', stdout=out)
        mock_apply.assert_called_with(pct=None, dry_run=True, use_ai=True)

    @mock.patch('portfolio.emails.send_html_email')
    def test_land_appraisal_email_rendering_and_dispatch(self, mock_email):
        from portfolio.emails import build_land_appraisal_context, send_land_appraisal_email
        from portfolio.land_appraisal import LandAppraisalSynthesis
        from django.template.loader import render_to_string

        appraisal = LandAppraisalSynthesis(
            holding_id=self.plot.id,
            holding_name=self.plot.name,
            closing_fy="FY 2025-26",
            current_valuation_inr=12000000.0,
            recommended_appreciation_pct=5.5,
            new_valuation_inr=12660000.0,
            net_value_increase_inr=660000.0,
            implied_rate_per_sq_yd_inr=50640.0,
            conservative_margin_of_safety_pct=3.0,
            methodology_summary="Grounded at 5.5% net after fiduciary haircuts.",
            key_drivers=["Jewar Airport Phase 1 progress"],
            risk_haircuts_applied=["Speculative broker markup discount"],
            confidence_score=0.9,
            model_chain_used="gemini-grounding -> argon-auditor -> gemini-4-argon",
        )
        results = [{
            'holding': self.plot,
            'old': Decimal('12000000'),
            'new': Decimal('12660000'),
            'pct': Decimal('5.50'),
            'appraisal': appraisal,
            'skipped': False,
        }]

        # Context builder
        ctx = build_land_appraisal_context(results, "FY 2025-26", group=self.group)
        self.assertTrue(ctx['has_revaluations'])
        self.assertEqual(ctx['primary']['holding'].name, self.plot.name)
        self.assertEqual(ctx['total_gain'], Decimal('660000'))

        # Template render
        html = render_to_string('emails/land_appraisal.html', ctx)
        self.assertIn("Yamuna Expressway Sector 22D Plot", html)
        self.assertIn("1,26,60,000", html)
        self.assertIn("YEIDA Fiduciary Valuation Certificate", html)

        # Dispatch
        ok, msg = send_land_appraisal_email(results, "FY 2025-26", group=self.group, target_email="family@example.com")
        self.assertTrue(ok)
        mock_email.assert_called_once()
        subject, body, html_out, recipients = mock_email.call_args[0]
        self.assertIn("Vault Real Estate Revaluation", subject)
        self.assertEqual(recipients, ["family@example.com"])

    @mock.patch('portfolio.management.commands.appreciate_land.apply_annual_land_appreciation')
    @mock.patch('portfolio.emails.send_land_appraisal_email')
    def test_command_triggers_email(self, mock_email, mock_apply):
        from django.core.management import call_command
        from io import StringIO

        mock_apply.return_value = ("FY 2025-26", [{
            'holding': self.plot,
            'old': Decimal('12000000'),
            'new': Decimal('12660000'),
            'pct': Decimal('5.50'),
            'appraisal': None,
            'skipped': False,
        }])
        mock_email.return_value = (True, "Email dispatched")

        # 1. Live run sends email
        out = StringIO()
        call_command('appreciate_land', stdout=out)
        mock_email.assert_called_once()

        # 2. --no-email suppresses email
        mock_email.reset_mock()
        out = StringIO()
        call_command('appreciate_land', '--no-email', stdout=out)
        mock_email.assert_not_called()

        # 3. --dry-run suppresses email by default
        mock_email.reset_mock()
        out = StringIO()
        call_command('appreciate_land', '--dry-run', stdout=out)
        mock_email.assert_not_called()

        # 4. --dry-run with --send-email sends email
        mock_email.reset_mock()
        out = StringIO()
        call_command('appreciate_land', '--dry-run', '--send-email', stdout=out)
        mock_email.assert_called_once()

    @mock.patch('portfolio.land_appraisal.gateway.generate_structured')
    def test_dag_stages_use_argon_in_production(self, mock_gen):
        from portfolio.land_appraisal import (
            GroundedMarketComps,
            DeepSeekAuditorReview,
            LandAppraisalSynthesis,
            discover_land_market_comps,
            run_deepseek_auditor_review,
            synthesize_land_appreciation,
        )

        # Stage 1 in prod
        mock_gen.return_value = GroundedMarketComps(
            locality="Sector 22D",
            city="Greater Noida",
            median_portal_ask_per_sq_yd=65000.0,
            circle_rate_floor_per_sq_yd=35000.0,
        )
        comps = discover_land_market_comps(self.plot, is_debug=False)
        _, kwargs1 = mock_gen.call_args
        self.assertEqual(kwargs1.get('model'), 'gemini-4-argon')
        self.assertEqual(kwargs1.get('thinking_level'), 'HIGH')

        # Stage 2 in prod
        mock_gen.reset_mock()
        mock_gen.return_value = DeepSeekAuditorReview(
            gross_market_growth_pct=8.5,
            conservative_appreciation_ceiling_pct=5.5,
            auditor_verdict="Audited",
        )
        auditor = run_deepseek_auditor_review(self.plot, comps, is_debug=False)
        _, kwargs2 = mock_gen.call_args
        self.assertEqual(kwargs2.get('model'), 'gemini-4-argon')
        self.assertEqual(kwargs2.get('thinking_level'), 'HIGH')

        # Stage 3 in prod
        mock_gen.reset_mock()
        mock_gen.return_value = LandAppraisalSynthesis(
            holding_id=self.plot.id,
            holding_name=self.plot.name,
            closing_fy="FY 2025-26",
            current_valuation_inr=12000000.0,
            recommended_appreciation_pct=5.5,
            new_valuation_inr=12660000.0,
            net_value_increase_inr=660000.0,
            methodology_summary="Prod Argon DAG synthesis",
        )
        synth = synthesize_land_appreciation(self.plot, comps, auditor, "FY 2025-26", is_debug=False)
        _, kwargs3 = mock_gen.call_args
        self.assertEqual(kwargs3.get('model'), 'gemini-4-argon')
        self.assertEqual(kwargs3.get('thinking_level'), 'HIGH')
        self.assertIn("gemini-4-argon", synth.model_chain_used)




