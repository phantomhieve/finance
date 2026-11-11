"""Security regression tests for portfolio vault unlock, RBAC, feature flags, WebAuthn, and forms."""
import datetime
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from portfolio.forms import NPSEntryForm, RealEstateHoldingForm
from portfolio.models import NPSEntry, RealEstateHolding
from tracker.models import AccountGroup, User, WebAuthnCredential


class PortfolioSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.group = AccountGroup.objects.create(name="SecVaultGroup")
        self.group.set_portfolio_password("CorrectHorseBatteryStaple1!")
        self.group.save()
        self.group.config.feature_portfolio = True
        self.group.config.feature_jewellery = True
        self.group.config.feature_expenses = True
        self.group.config.feature_real_estate = True
        self.group.config.feature_ai_insights = True
        self.group.config.save()

        self.primary = User.objects.create_user(
            username="v_primary", password="pw", user_type="PRIMARY", group=self.group
        )
        self.spouse = User.objects.create_user(
            username="v_spouse", password="pw", user_type="ACCOUNT_HOLDER", group=self.group
        )
        self.landlord = User.objects.create_user(
            username="v_landlord", password="pw", user_type="LANDLORD", group=self.group
        )
        # Register dummy WebAuthn credentials so successful unlock issues 302 redirect directly
        WebAuthnCredential.objects.create(
            user=self.primary, credential_id=b'cred-primary', public_key=b'pk-primary'
        )
        WebAuthnCredential.objects.create(
            user=self.spouse, credential_id=b'cred-spouse', public_key=b'pk-spouse'
        )

        self.other_group = AccountGroup.objects.create(name="OtherVaultGroup")
        self.other_group.set_portfolio_password("OtherSecret123!")
        self.other_group.save()
        self.outsider = User.objects.create_user(
            username="v_outsider", password="pw", user_type="PRIMARY", group=self.other_group
        )

    def tearDown(self):
        cache.clear()

    def test_landlord_forbidden_from_vault_unlock_oracle_and_dos(self):
        self.client.force_login(self.landlord)
        resp_get = self.client.get(reverse('portfolio_unlock'))
        self.assertEqual(resp_get.status_code, 403)
        resp_post = self.client.post(reverse('portfolio_unlock'), {
            'password': 'CorrectHorseBatteryStaple1!',
        })
        self.assertEqual(resp_post.status_code, 403)

    def test_vault_unlock_blocks_open_redirects(self):
        self.client.force_login(self.primary)
        malicious_nexts = [
            'https://evil.com/phish',
            '//evil.com/phish',
            r'\\evil.com',
            '/portfolio/\r\nSet-Cookie: hacked=1',
        ]
        for bad_next in malicious_nexts:
            resp = self.client.post(reverse('portfolio_unlock'), {
                'password': 'CorrectHorseBatteryStaple1!',
                'next': bad_next,
            })
            self.assertEqual(resp.status_code, 302, bad_next)
            self.assertEqual(resp['Location'], reverse('portfolio_tracker'), bad_next)

    def test_vault_password_rotation_invalidates_existing_unlocked_sessions(self):
        self.client.force_login(self.primary)
        resp = self.client.post(reverse('portfolio_unlock'), {
            'password': 'CorrectHorseBatteryStaple1!',
            'next': '/portfolio/',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.get(reverse('portfolio_tracker')).status_code, 200)
        self.assertEqual(self.client.get(reverse('expenses_home')).status_code, 200)

        # Rotate the household vault password: unlocked session must immediately re-lock
        self.group.set_portfolio_password("RotatedVaultSecret99!")
        self.group.save()

        resp_port = self.client.get(reverse('portfolio_tracker'))
        self.assertEqual(resp_port.status_code, 302)
        self.assertIn(reverse('portfolio_unlock'), resp_port['Location'])

        resp_exp = self.client.get(reverse('expenses_home'))
        self.assertEqual(resp_exp.status_code, 302)
        self.assertIn(reverse('portfolio_unlock'), resp_exp['Location'])

    def test_vault_unlock_rate_limiting_per_user_and_household(self):
        # 5 wrong attempts by ACCOUNT_HOLDER locks out ACCOUNT_HOLDER, but NOT PRIMARY
        self.client.force_login(self.spouse)
        for _ in range(5):
            self.client.post(reverse('portfolio_unlock'), {'password': 'wrong'})
        resp_spouse_good = self.client.post(reverse('portfolio_unlock'), {
            'password': 'CorrectHorseBatteryStaple1!',
            'next': '/jewellery/',
        })
        # Locked out -> renders 200 with lockout error instead of 302 redirect
        self.assertEqual(resp_spouse_good.status_code, 200)
        self.assertContains(resp_spouse_good, "Too many failed attempts")

        # PRIMARY can still unlock because household budget (10) is not exhausted
        primary_client = self.client_class()
        primary_client.force_login(self.primary)
        resp_primary_ok = primary_client.post(reverse('portfolio_unlock'), {
            'password': 'CorrectHorseBatteryStaple1!',
            'next': '/portfolio/',
        })
        self.assertEqual(resp_primary_ok.status_code, 302)
        self.assertEqual(resp_primary_ok['Location'], '/portfolio/')

    def test_webauthn_endpoints_reject_non_dict_json_cleanly(self):
        self.client.force_login(self.primary)
        self.client.post(reverse('portfolio_unlock'), {
            'password': 'CorrectHorseBatteryStaple1!',
        })
        for url_name in ('webauthn_register_complete', 'webauthn_auth_complete', 'webauthn_remove'):
            for payload in ('[1, 2, 3]', '12345', '"str"', 'null'):
                resp = self.client.post(
                    reverse(url_name),
                    data=payload,
                    content_type='application/json',
                )
                self.assertEqual(resp.status_code, 400, f"{url_name} with {payload}")

    def test_disabled_real_estate_and_ai_insights_features_return_404(self):
        re_item = RealEstateHolding.objects.create(
            group=self.group,
            name="Plot A",
            property_type="PLOT_LAND",
            area_value=Decimal('200'),
            locality="Sector 150",
            purchase_date=datetime.date(2024, 1, 15),
            purchase_price=Decimal('5000000'),
            current_valuation=Decimal('6000000'),
        )
        self.group.config.feature_real_estate = False
        self.group.config.feature_ai_insights = False
        self.group.config.save()

        self.client.force_login(self.primary)
        self.client.post(reverse('portfolio_unlock'), {'password': 'CorrectHorseBatteryStaple1!'})

        self.assertEqual(self.client.get(reverse('real_estate_detail')).status_code, 404)
        self.assertEqual(self.client.post(reverse('add_real_estate'), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('edit_real_estate', args=[re_item.pk]), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('delete_real_estate', args=[re_item.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('update_real_estate_valuation', args=[re_item.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('real_estate_llm_prompt_json', args=[re_item.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse('toggle_baby', args=['realestateholding', re_item.pk])).status_code,
            404,
        )
        self.assertEqual(self.client.post(reverse('generate_insights')).status_code, 404)

    def test_pf_fy_entry_bounds_reject_extreme_years_without_500(self):
        from portfolio.models import PFEntry
        self.client.force_login(self.primary)
        self.client.post(reverse('portfolio_unlock'), {'password': 'CorrectHorseBatteryStaple1!'})

        for bad_year in ('99999', '-50', '0'):
            resp = self.client.post(reverse('save_pf_fy_entry'), {
                'fy_year': bad_year,
                'account_name': 'Main EPF',
                'contribution': '1000',
            })
            self.assertEqual(resp.status_code, 302)
            self.assertFalse(PFEntry.objects.filter(group=self.group).exists())
            resp_del = self.client.post(reverse('delete_pf_fy_entry'), {
                'fy_year': bad_year,
                'account_name': 'Main EPF',
            })
            self.assertEqual(resp_del.status_code, 302)

    def test_forms_prevent_javascript_url_and_cross_tenant_nps_leak(self):
        # 1. RealEstateHoldingForm blocks javascript: scheme in google_maps_url
        form = RealEstateHoldingForm(data={
            'name': 'Plot X',
            'property_type': 'PLOT_LAND',
            'status': 'VACANT_PLOT',
            'acquisition_type': 'PURCHASED',
            'area_value': '200',
            'area_unit': 'GAJ',
            'city': 'Noida',
            'state': 'Uttar Pradesh',
            'locality': 'Sector 150',
            'purchase_date': '2024-01-15',
            'purchase_price': '1000000',
            'stamp_duty_charges': '0',
            'current_valuation': '1200000',
            'monthly_rental_income': '0',
            'google_maps_url': 'javascript:alert(1)',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('google_maps_url', form.errors)

        # 2. NPSEntryForm without group must NOT read another household's NPSEntry balance
        NPSEntry.objects.create(
            group=self.other_group,
            date=datetime.date(2026, 4, 1),
            contribution=Decimal('50000'),
            total_balance=Decimal('9999999'),
        )
        nps_form = NPSEntryForm(data={
            'date': '2026-05-01',
            'contribution': '10000',
            'interest_earned': '0',
            'total_balance': '0',
        })
        self.assertTrue(nps_form.is_valid(), nps_form.errors)
        self.assertNotEqual(nps_form.cleaned_data['total_balance'], Decimal('10009999'))
        self.assertEqual(nps_form.cleaned_data['total_balance'], Decimal('10000'))
