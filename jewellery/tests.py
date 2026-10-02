import time
import shutil
import tempfile
from decimal import Decimal
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from tracker.models import AccountGroup, User
from portfolio.models import CommodityPrice
from jewellery.models import JewelleryItem

_TEST_MEDIA = tempfile.mkdtemp(prefix='jewellery_test_media_')


@override_settings(MEDIA_ROOT=_TEST_MEDIA)
class JewelleryTrackerTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TEST_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # Create an AccountGroup
        self.group = AccountGroup.objects.create(name="Test Group")
        self.group.set_portfolio_password("portfolio123")
        self.group.save()
        self.group.config.feature_jewellery = True
        self.group.config.save()

        # Create a user
        self.user = User.objects.create_user(
            username="testuser",
            password="password123",
            user_type="PRIMARY",
            group=self.group
        )

        # Set up CommodityPrices
        self.gold_price = CommodityPrice.objects.create(
            commodity_type="GOLD",
            rate_per_gram=Decimal("6000.00")
        )
        self.silver_price = CommodityPrice.objects.create(
            commodity_type="SILVER",
            rate_per_gram=Decimal("75.00")
        )

        # Set up client and authenticate
        self.client = Client()
        self.client.login(username="testuser", password="password123")

        # Bypass portfolio password unlock gating in session
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

    def test_dashboard_loads_empty(self):
        response = self.client.get(reverse('jewellery_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No jewellery items found")

    def _count_dashboard_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('jewellery_dashboard'))
        return len(ctx.captured_queries)

    def test_dashboard_queries_do_not_grow_with_items(self):
        def add(n, location):
            for _ in range(n):
                JewelleryItem.objects.create(group=self.group, category='RING', metal_type='GOLD',
                                             purity='22k', weight_grams=Decimal('5'), location=location)
        add(2, 'BANK_LOCKER')
        few = self._count_dashboard_queries()
        add(10, 'HOME_SAFE')
        response = self.client.get(reverse('jewellery_dashboard'))
        self.assertEqual(self._count_dashboard_queries(), few)
        # 12 × 5g × ₹6000 × 0.916, split 2:10 between locker and home
        self.assertEqual(response.context['total_estimated_value'], Decimal('329760.00'))
        self.assertEqual([loc['pct'] for loc in response.context['value_by_location']], [17, 83])
        self.assertContains(response, "Jewellery Collection")

    def test_add_item_and_calculations(self):
        # Post to add_item
        post_data = {
            'category': 'RING',
            'location': 'BANK_LOCKER',
            'metal_type': 'GOLD',
            'purity': '22k',
            'weight_grams': '10.00',
            'notes': ''
        }
        response = self.client.post(reverse('add_jewellery'), data=post_data)
        self.assertRedirects(response, reverse('jewellery_dashboard'))

        # Check in DB
        self.assertEqual(JewelleryItem.objects.count(), 1)
        item = JewelleryItem.objects.first()
        self.assertEqual(item.location, 'BANK_LOCKER')
        self.assertEqual(item.display_label, '22k Gold Ring')
        self.assertEqual(item.category_icon, 'diamond')
        self.assertEqual(item.weight_grams, Decimal('10.00'))
        
        # Purity factor is 22k (0.916), gold rate is 6000.00. 
        # Estimated value = 10 * 6000 * 0.916 = 54960.00
        self.assertEqual(item.estimated_value, Decimal('54960.00'))
        self.assertEqual(item.pnl, Decimal('0.00'))

        # Now load dashboard to check numbers
        response = self.client.get(reverse('jewellery_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "54,960") # Indian formatted total value

    def test_edit_item(self):
        # Create an item first
        item = JewelleryItem.objects.create(
            group=self.group,
            category='CHAIN',
            metal_type='GOLD',
            purity='18k',
            weight_grams=Decimal('20.00'),
            location='HOME_SAFE'
        )
        # Edit details
        edit_data = {
            'category': 'CHAIN',
            'location': 'BANK_LOCKER',
            'metal_type': 'GOLD',
            'purity': '18k',
            'weight_grams': '20.00',
            'notes': 'Resized chain'
        }
        response = self.client.post(
            reverse('edit_jewellery', kwargs={'pk': item.pk}),
            data=edit_data
        )
        self.assertRedirects(response, reverse('jewellery_dashboard'))

        item.refresh_from_db()
        self.assertEqual(item.location, 'BANK_LOCKER')
        # Estimated value = 20 * 6000 * 0.750 = 90000.00
        self.assertEqual(item.estimated_value, Decimal('90000.00'))
        self.assertEqual(item.pnl, Decimal('0.00'))

    def test_diamond_other_valuation(self):
        # DIAMOND_OTHER should use GOLD rate (6000.00) and support gold purity
        item = JewelleryItem.objects.create(
            group=self.group,
            category='RING',
            metal_type='DIAMOND_OTHER',
            purity='18k',
            weight_grams=Decimal('10.00'),
            location='BANK_LOCKER'
        )
        # Purity factor is 18k (0.750), gold rate is 6000.00. 
        # Estimated value = 10 * 6000 * 0.750 = 45000.00
        self.assertEqual(item.estimated_value, Decimal('45000.00'))
        self.assertEqual(item.pnl, Decimal('0.00'))

    def test_delete_item(self):
        item = JewelleryItem.objects.create(
            group=self.group,
            category='COIN',
            metal_type='SILVER',
            purity='999',
            weight_grams=Decimal('100.00'),
            location='HOME_SAFE'
        )
        response = self.client.post(reverse('delete_jewellery', kwargs={'pk': item.pk}))
        self.assertRedirects(response, reverse('jewellery_dashboard'))
        self.assertEqual(JewelleryItem.objects.count(), 0)

    def test_serve_photo_secure(self):
        # Create item with dummy photo
        photo_file = SimpleUploadedFile("ring.jpg", b"file_content", content_type="image/jpeg")
        item = JewelleryItem.objects.create(
            group=self.group,
            category='RING',
            metal_type='GOLD',
            purity='22k',
            weight_grams=Decimal('5.00'),
            location='BANK_LOCKER',
            photo=photo_file
        )

        response = self.client.get(reverse('jewellery_photo', kwargs={'pk': item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"file_content")

        # Log in as a different user in a different group to check secure access control
        other_group = AccountGroup.objects.create(name="Other Group")
        other_group.config.feature_jewellery = True
        other_group.config.save()
        other_user = User.objects.create_user(
            username="otheruser",
            password="password123",
            user_type="PRIMARY",
            group=other_group
        )
        self.client.force_login(other_user)
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

        # Should get 404 since item belongs to self.group, not other_group!
        response = self.client.get(reverse('jewellery_photo', kwargs={'pk': item.pk}))
        self.assertEqual(response.status_code, 404)

    def test_heic_photo_conversion(self):
        from io import BytesIO
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
        
        im = Image.new("RGB", (10, 10), color="blue")
        heif_io = BytesIO()
        im.save(heif_io, format="HEIF")
        heif_io.seek(0)
        
        photo_file = SimpleUploadedFile("iphone_photo.heic", heif_io.read(), content_type="image/heic")
        
        post_data = {
            'category': 'RING',
            'location': 'BANK_LOCKER',
            'metal_type': 'GOLD',
            'purity': '22k',
            'weight_grams': '5.00',
            'photo': photo_file
        }
        response = self.client.post(reverse('add_jewellery'), data=post_data)
        self.assertRedirects(response, reverse('jewellery_dashboard'))
        
        item = JewelleryItem.objects.latest('created_at')
        self.assertTrue(item.photo.name.endswith('.jpg'))
        self.assertFalse(item.photo.name.endswith('.heic'))


class JewelleryAccessControlTests(TestCase):
    def setUp(self):
        self.group = AccountGroup.objects.create(name="Household")
        self.group.config.feature_jewellery = True
        self.group.config.save()
        self.spouse = User.objects.create_user(
            username="spouse", password="pw-123456", user_type="ACCOUNT_HOLDER", group=self.group)
        self.client = Client()
        self.client.force_login(self.spouse)
        session = self.client.session
        session['portfolio_unlocked_at'] = time.time()
        session.save()

    def test_account_holder_cannot_add_or_edit(self):
        item = JewelleryItem.objects.create(
            group=self.group, category="RING", metal_type="GOLD", purity="22K", weight_grams=Decimal("5"))
        add = self.client.post(reverse('add_jewellery'), {'category': 'RING'})
        edit = self.client.post(reverse('edit_jewellery', args=[item.pk]), {'category': 'RING'})
        self.assertEqual(add.status_code, 403)
        self.assertEqual(edit.status_code, 403)

    def test_disabled_feature_returns_404(self):
        config = self.group.config
        config.feature_jewellery = False
        config.save()
        self.assertEqual(self.client.get(reverse('jewellery_dashboard')).status_code, 404)
