import datetime
import json
import time
from decimal import Decimal

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

        # 5. Delete record via generic delete_record MCP tool
        del_res = json.loads(mcp_srv.delete_record(
            model_name="portfolio.RealEstateHolding",
            record_id=holding_id,
        ))
        self.assertEqual(del_res['status'], 'deleted')
        self.assertEqual(RealEstateHolding.objects.count(), 0)
