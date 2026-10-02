import os
import uuid
from decimal import Decimal
from django.db import models
from portfolio.models import CommodityPrice


def jewellery_photo_path(instance, filename):
    """Store uploads under a random, opaque filename to avoid collisions and
    to never trust/reuse the user-supplied name. Extension is preserved
    (already validated by the form's allowlist)."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
        ext = '.jpg'
    return f"jewellery_photos/{uuid.uuid4().hex}{ext}"


class JewelleryItem(models.Model):
    CATEGORY_CHOICES = (
        ('CHAIN', 'Chain'),
        ('LOCKET', 'Locket'),
        ('NECKLACE', 'Necklace'),
        ('RING', 'Ring'),
        ('BANGLE', 'Bangle'),
        ('BRACELET', 'Bracelet'),
        ('EARRINGS', 'Earrings'),
        ('COIN', 'Coin'),
        ('OTHER', 'Other'),
    )

    # category -> (material-symbol icon, hue) used for colour-coded type chips.
    CATEGORY_META = {
        'CHAIN':    ('link', 210),
        'LOCKET':   ('favorite', 340),
        'NECKLACE': ('workspace_premium', 280),
        'RING':     ('diamond', 45),
        'BANGLE':   ('radio_button_unchecked', 160),
        'BRACELET': ('blur_circular', 190),
        'EARRINGS': ('water_drop', 320),
        'COIN':     ('toll', 38),
        'OTHER':    ('category', 230),
    }

    METAL_CHOICES = (
        ('GOLD', 'Gold'),
        ('SILVER', 'Silver'),
        ('PLATINUM', 'Platinum'),
        ('DIAMOND_OTHER', 'Diamond/Other'),
    )

    GOLD_PURITY_CHOICES = (
        ('24k', '24k (999)'),
        ('22k', '22k (916)'),
        ('18k', '18k (750)'),
        ('14k', '14k (585)'),
    )
    SILVER_PURITY_CHOICES = (
        ('999', '999 (Fine Silver)'),
        ('925', '925 (Sterling)'),
        ('900', '900'),
        ('800', '800'),
    )
    PURITY_CHOICES = GOLD_PURITY_CHOICES + SILVER_PURITY_CHOICES

    LOCATION_CHOICES = (
        ('BANK_LOCKER', 'Bank Locker'),
        ('HOME_SAFE', 'Home Safe'),
    )

    # Approximate purity → fineness multiplier used for valuation.
    PURITY_FACTORS = {
        '24k': Decimal('1.000'),
        '22k': Decimal('0.916'),
        '18k': Decimal('0.750'),
        '14k': Decimal('0.585'),
        '999': Decimal('1.000'),
        '925': Decimal('0.925'),
        '900': Decimal('0.900'),
        '800': Decimal('0.800'),
    }

    group = models.ForeignKey(
        'tracker.AccountGroup',
        on_delete=models.CASCADE,
        related_name='jewellery_items',
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    metal_type = models.CharField(max_length=20, choices=METAL_CHOICES, default='GOLD')
    purity = models.CharField(max_length=20, choices=PURITY_CHOICES, blank=True)
    weight_grams = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='BANK_LOCKER')

    photo = models.ImageField(upload_to=jewellery_photo_path, null=True, blank=True)

    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, help_text="Total price paid")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.display_label

    @property
    def display_label(self):
        """Human label built from attributes (replaces the old free-text name)."""
        parts = []
        if self.purity:
            parts.append(self.get_purity_display().split(' ')[0])
        parts.append(self.get_metal_type_display())
        parts.append(self.get_category_display())
        return ' '.join(p for p in parts if p)

    @property
    def category_icon(self):
        return self.CATEGORY_META.get(self.category, ('category', 230))[0]

    @property
    def category_hue(self):
        return self.CATEGORY_META.get(self.category, ('category', 230))[1]

    @property
    def search_blob(self):
        """Lower-cased text used for substring search matching."""
        bits = [
            self.notes,
            self.get_category_display(),
            self.get_metal_type_display(),
            self.get_location_display(),
            self.purity,
        ]
        return ' '.join(b for b in bits if b).lower()

    @staticmethod
    def current_rates():
        """{'GOLD': rate, 'SILVER': rate} per gram — one query."""
        return dict(CommodityPrice.objects.filter(commodity_type__in=('GOLD', 'SILVER'))
                    .values_list('commodity_type', 'rate_per_gram'))

    @classmethod
    def attach_rates(cls, items, rates=None):
        """Share one rate lookup across many items so ``estimated_value`` doesn't query per item."""
        rates = cls.current_rates() if rates is None else rates
        for item in items:
            item._rates = rates
        return rates

    @property
    def estimated_value(self):
        if self.metal_type in ['GOLD', 'DIAMOND_OTHER']:
            price_type = 'GOLD'
        elif self.metal_type == 'SILVER':
            price_type = 'SILVER'
        else:
            return Decimal('0.00')

        if not self.weight_grams:
            return Decimal('0.00')

        rates = getattr(self, '_rates', None)
        if rates is None:
            rates = self.current_rates()
        rate = rates.get(price_type)
        if not rate:
            return Decimal('0.00')

        purity_factor = self.PURITY_FACTORS.get(self.purity, Decimal('1.0'))
        return (self.weight_grams * rate * purity_factor).quantize(Decimal('0.01'))

    @property
    def pnl(self):
        return Decimal('0.00')
