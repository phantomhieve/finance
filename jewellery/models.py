from django.db import models
from portfolio.models import CommodityPrice

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

    group = models.ForeignKey(
        'tracker.AccountGroup',
        on_delete=models.CASCADE,
        related_name='jewellery_items',
    )
    name = models.CharField(max_length=200, help_text="Short description (e.g. Wedding Ring)")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    metal_type = models.CharField(max_length=20, choices=METAL_CHOICES, default='GOLD')
    purity = models.CharField(max_length=20, choices=PURITY_CHOICES, blank=True)
    weight_grams = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    location = models.CharField(max_length=20, choices=LOCATION_CHOICES, default='BANK_LOCKER')
    photo = models.ImageField(upload_to='jewellery_photos/', null=True, blank=True)
    
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True, help_text="Total price paid")
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_metal_type_display()})"

    @property
    def estimated_value(self):
        from decimal import Decimal
        if self.metal_type not in ['GOLD', 'SILVER'] or not self.weight_grams:
            return self.purchase_price or Decimal('0.00')  # Fallback
            
        price_obj = CommodityPrice.objects.filter(commodity_type=self.metal_type).first()
        if not price_obj:
            return Decimal('0.00')
            
        rate = price_obj.rate_per_gram
        
        # Approximate purity multiplier
        purity_factor = Decimal('1.0')
        if self.purity == '22k': purity_factor = Decimal('0.916')
        elif self.purity == '18k': purity_factor = Decimal('0.750')
        elif self.purity == '14k': purity_factor = Decimal('0.585')
        elif self.purity == '999': purity_factor = Decimal('1.000')
        elif self.purity == '925': purity_factor = Decimal('0.925')
        elif self.purity == '900': purity_factor = Decimal('0.900')
        elif self.purity == '800': purity_factor = Decimal('0.800')

        return (self.weight_grams * rate * purity_factor).quantize(Decimal('0.01'))

    @property
    def pnl(self):
        from decimal import Decimal
        return self.estimated_value - (self.purchase_price or Decimal('0.00'))
