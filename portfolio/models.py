from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Index
from django.utils import timezone


class PnlMixin:
    """Shared P&L properties for models with purchase_value and current_value."""

    @property
    def pnl(self):
        return self.current_value - self.purchase_value

    @property
    def pnl_pct(self):
        if self.purchase_value:
            return (self.pnl / self.purchase_value * 100).quantize(Decimal('0.01'))
        return Decimal('0')


class ZerodhaAccount(models.Model):
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='zerodha_accounts', null=True, blank=True,
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    sheet_id = models.CharField(
        max_length=200, blank=True,
        help_text="Google Sheets spreadsheet ID",
    )
    sheet_range_stocks = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Sheet name / range for stock holdings",
    )
    sheet_range_index_mf = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Sheet name / range for index mutual funds",
    )
    sheet_range_other_mf = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Sheet name / range for other mutual funds",
    )
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StockHolding(PnlMixin, models.Model):
    account = models.ForeignKey(
        ZerodhaAccount, on_delete=models.CASCADE, related_name='stock_holdings',
    )
    symbol = models.CharField(max_length=50)
    quantity = models.IntegerField(default=0)
    purchase_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['symbol']
        constraints = [
            models.UniqueConstraint(fields=['account', 'symbol'], name='unique_account_symbol'),
        ]

    def __str__(self):
        return f"{self.account.name} — {self.symbol}"


class MutualFundHolding(PnlMixin, models.Model):
    FUND_TYPE_CHOICES = (
        ('INDEX', 'Index Fund'),
        ('OTHER', 'Other Mutual Fund'),
    )

    account = models.ForeignKey(
        ZerodhaAccount, on_delete=models.CASCADE, related_name='mf_holdings',
    )
    fund_name = models.CharField(max_length=300)
    fund_type = models.CharField(max_length=10, choices=FUND_TYPE_CHOICES)
    units = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    purchase_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['fund_name']
        indexes = [
            Index(fields=['account', 'fund_type']),
        ]

    def __str__(self):
        return f"{self.account.name} — {self.fund_name[:60]}"


class FinancialGoal(models.Model):
    """Portfolio net-worth target for an Indian FY (or long term).

    Distinct from tracker.FinancialGoal which tracks monthly savings.
    Once the FY closes, the goal is judged on ``closing_value`` (portfolio value
    in the March snapshot) so the achieved / missed verdict is frozen.
    """
    LONG_TERM = 'Long Term'

    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='portfolio_goals', null=True, blank=True,
    )
    label = models.CharField(max_length=50, help_text="e.g. 50L, 1Cr")
    target_amount = models.DecimalField(max_digits=14, decimal_places=0)
    target_date = models.DateField(null=True, blank=True, help_text="Target date to achieve this goal (e.g. FY End: 2026-03-31)")
    achieved_at = models.DateField(null=True, blank=True,
                                   help_text="Auto-set when portfolio value first reaches the target")
    financial_year = models.CharField(
        max_length=30, blank=True,
        help_text="e.g. FY 2026-27 or Long Term",
    )
    closing_value = models.DecimalField(
        max_digits=14, decimal_places=0, null=True, blank=True,
        help_text="Portfolio value at FY close (from the March snapshot); locks the achieved/missed verdict",
    )
    notes = models.TextField(blank=True, help_text="Optional notes or comments for this goal")

    class Meta:
        ordering = ['target_date', 'target_amount']

    @property
    def fy_start(self):
        """FY start year (2026 for 'FY 2026-27'), or None for long-term goals."""
        from pftracker.utils import fy_start_from_label
        return fy_start_from_label(self.financial_year)

    @property
    def fy_end_date(self):
        start = self.fy_start
        return date(start + 1, 3, 31) if start is not None else None

    def save(self, *args, **kwargs):
        from pftracker.utils import fy_label, fy_start_year
        if not self.financial_year and self.target_date:
            self.financial_year = fy_label(fy_start_year(self.target_date))
        elif not self.target_date and self.fy_end_date:
            self.target_date = self.fy_end_date
        super().save(*args, **kwargs)

    def __str__(self):
        fy_suffix = f" ({self.financial_year})" if self.financial_year else ""
        return f"{self.label}{fy_suffix} — ₹{self.target_amount:,.0f}"


class EPFEntry(models.Model):
    ENTRY_TYPES = (
        ('CONTRIBUTION', 'Contribution'),
        ('INTEREST', 'Interest'),
    )
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='epf_entries', null=True, blank=True,
    )
    date = models.DateField()
    entry_type = models.CharField(max_length=15, choices=ENTRY_TYPES, default='CONTRIBUTION')
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'EPF Entry'
        verbose_name_plural = 'EPF Entries'
        indexes = [
            Index(fields=['group', '-date']),
        ]

    def __str__(self):
        return f"EPF {self.get_entry_type_display()} {self.date} — ₹{self.amount:,.0f}"


class PFEntry(models.Model):
    """Provident Fund / Public Provident Fund (PF / PPF) entry per family member."""
    ENTRY_TYPES = (
        ('CONTRIBUTION', 'Contribution'),
        ('INTEREST', 'Interest'),
    )
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='pf_entries', null=True, blank=True,
    )
    account_name = models.CharField(
        max_length=100,
        default='Atul',
        help_text="Family member / PF account holder (e.g. Atul, Kanika)",
    )
    date = models.DateField()
    entry_type = models.CharField(max_length=15, choices=ENTRY_TYPES, default='CONTRIBUTION')
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=255, blank=True)
    is_baby = models.BooleanField(
        default=False,
        help_text="Track in Child portfolio instead of master portfolio",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'PF Entry'
        verbose_name_plural = 'PF Entries'
        indexes = [
            Index(fields=['group', '-date']),
            Index(fields=['group', 'account_name']),
        ]

    def save(self, *args, **kwargs):
        if self.account_name:
            self.account_name = self.account_name.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"PF ({self.account_name}) {self.get_entry_type_display()} {self.date} — ₹{self.amount:,.0f}"



class NPSEntry(models.Model):
    """Each row is an update event. Latest row by date = current NPS state."""
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='nps_entries', null=True, blank=True,
    )
    date = models.DateField()
    contribution = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Money added in this update",
    )
    interest_earned = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Returns credited in this update",
    )
    total_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Running total after this update",
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'NPS Entry'
        verbose_name_plural = 'NPS Entries'
        indexes = [
            Index(fields=['group', '-date']),
        ]

    def __str__(self):
        return f"NPS {self.date} — ₹{self.total_balance:,.0f}"


class FixedDeposit(models.Model):
    COMPOUNDING_CHOICES = (
        ('SIMPLE', 'Simple Interest'),
        ('MONTHLY', 'Monthly'),
        ('QUARTERLY', 'Quarterly'),
        ('ANNUAL', 'Annual'),
    )

    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='fixed_deposits', null=True, blank=True,
    )
    name = models.CharField(max_length=200)
    account_name = models.CharField(
        max_length=100,
        help_text="e.g. Atul Acc, HUF Acc, Blue Green Web",
    )
    principal = models.DecimalField(max_digits=14, decimal_places=2)
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Annual interest rate in %",
    )
    compounding = models.CharField(
        max_length=10, choices=COMPOUNDING_CHOICES, default='QUARTERLY',
    )
    start_date = models.DateField()
    maturity_date = models.DateField()
    is_active = models.BooleanField(default=True)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_active', 'maturity_date']
        indexes = [
            Index(fields=['group', 'is_active']),
        ]

    def __str__(self):
        return f"FD: {self.name} — ₹{self.principal:,.0f} @ {self.interest_rate}%"

    @property
    def current_value(self):
        return compute_fd_value(
            self.principal, self.interest_rate, self.compounding,
            self.start_date, min(date.today(), self.maturity_date),
        )

    @property
    def maturity_value(self):
        return compute_fd_value(
            self.principal, self.interest_rate, self.compounding,
            self.start_date, self.maturity_date,
        )

    @property
    def interest_accrued(self):
        return self.current_value - self.principal

    @property
    def days_remaining(self):
        delta = self.maturity_date - date.today()
        return max(delta.days, 0)


def compute_fd_value(principal, rate_pct, compounding, start, end):
    """Compute FD value with interest accrual."""
    days = (end - start).days
    if days <= 0:
        return principal
    years = float(days) / 365.0
    r = float(rate_pct) / 100.0
    if compounding == 'SIMPLE':
        result = float(principal) * (1 + r * years)
        return Decimal(str(round(result, 2)))
    n_map = {'MONTHLY': 12, 'QUARTERLY': 4, 'ANNUAL': 1}
    n = n_map.get(compounding, 4)
    base = 1 + r / n
    exponent = n * years
    result = float(principal) * (base ** exponent)
    return Decimal(str(round(result, 2)))


class CashPosition(models.Model):
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='cash_positions', null=True, blank=True,
    )
    name = models.CharField(max_length=100, help_text="e.g. Kanika Acc, Cash lent Reshu")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=255, blank=True)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — ₹{self.amount:,.0f}"


class BondHolding(models.Model):
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='bond_holdings', null=True, blank=True,
    )
    account_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=255, blank=True)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['account_name']

    def __str__(self):
        return f"Bond: {self.account_name} — ₹{self.amount:,.0f}"


class CryptoHolding(models.Model):
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='crypto_holdings', null=True, blank=True,
    )
    name = models.CharField(max_length=100, default='Crypto')
    amount_invested = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remarks = models.CharField(max_length=255, blank=True)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} — ₹{self.current_value:,.0f}"

    @property
    def pnl(self):
        return self.current_value - self.amount_invested


class CommodityHolding(PnlMixin, models.Model):
    COMMODITY_CHOICES = (
        ('GOLD', 'Gold'),
        ('SILVER', 'Silver'),
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

    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='commodity_holdings', null=True, blank=True,
    )
    commodity_type = models.CharField(max_length=10, choices=COMMODITY_CHOICES)
    description = models.CharField(
        max_length=200,
        help_text="e.g. 20gm Coin - 1 (24k)",
    )
    purity = models.CharField(
        max_length=20, blank=True, choices=PURITY_CHOICES, default='24k',
    )
    weight_grams = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_price_per_gram = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Price per gram at the time of purchase (INR)",
    )
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['commodity_type', '-weight_grams']

    def __str__(self):
        return f"{self.get_commodity_type_display()}: {self.description}"

    @property
    def purchase_value(self):
        return (self.weight_grams * self.purchase_price_per_gram).quantize(Decimal('0.01'))

    @property
    def current_rate(self):
        if hasattr(self, '_cached_rate'):
            return self._cached_rate
        price = CommodityPrice.objects.filter(
            commodity_type=self.commodity_type
        ).order_by('-fetched_at').first()
        return price.rate_per_gram if price else Decimal('0')

    @property
    def current_value(self):
        return (self.weight_grams * self.current_rate).quantize(Decimal('0.01'))


class USStockHolding(models.Model):
    """Track US stock RSU holdings (e.g. Uber) with USD→INR conversion."""

    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='us_stock_holdings', null=True, blank=True,
    )
    symbol = models.CharField(max_length=20, default='UBER')
    company_name = models.CharField(max_length=200, default='Employer Corp')
    quantity = models.IntegerField(default=0)
    vest_date = models.DateField(help_text="Date RSUs were vested / added")
    purchase_price_usd = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Stock price per share in USD at vest date",
    )
    current_price_usd = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Latest stock price per share in USD",
    )
    purchase_usd_inr = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="USD/INR exchange rate at vest date",
    )
    current_usd_inr = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Latest USD/INR exchange rate",
    )
    last_refreshed = models.DateTimeField(null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    is_baby = models.BooleanField(default=False, help_text="Track in Child portfolio instead of master portfolio")

    class Meta:
        ordering = ['-vest_date']

    def __str__(self):
        return f"{self.symbol} × {self.quantity} ({self.vest_date})"

    @property
    def purchase_value(self):
        return (self.quantity * self.purchase_price_usd * self.purchase_usd_inr).quantize(Decimal('0.01'))

    @property
    def current_value(self):
        return (self.quantity * self.current_price_usd * self.current_usd_inr).quantize(Decimal('0.01'))

    @property
    def pnl(self):
        return self.current_value - self.purchase_value

    @property
    def pnl_pct(self):
        if self.purchase_value:
            return (self.pnl / self.purchase_value * 100).quantize(Decimal('0.01'))
        return Decimal('0')

class CommodityPrice(models.Model):
    """Cached commodity price — one row per commodity type, updated on refresh."""
    COMMODITY_CHOICES = (
        ('GOLD', 'Gold'),
        ('SILVER', 'Silver'),
    )

    commodity_type = models.CharField(max_length=10, choices=COMMODITY_CHOICES, unique=True)
    rate_per_gram = models.DecimalField(max_digits=12, decimal_places=2)
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['commodity_type']

    def __str__(self):
        return f"{self.get_commodity_type_display()} — ₹{self.rate_per_gram}/g ({self.fetched_at:%Y-%m-%d %H:%M})"


class PortfolioInsight(models.Model):
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='portfolio_insights', null=True, blank=True,
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    model_used = models.CharField(max_length=50)
    prompt_data = models.JSONField()
    insights = models.JSONField()

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f"Insight {self.generated_at:%Y-%m-%d %H:%M}"


class InsightGenerationSettings(models.Model):
    """Singleton (pk=1): production cooldown between AI insight generations."""

    cooldown_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Minimum calendar days between runs per AccountGroup (ignored when DEBUG=True).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI insight cooldown"
        verbose_name_plural = "AI insight cooldown"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'cooldown_days': 30})
        return obj

    def __str__(self):
        return f"{self.cooldown_days} day cooldown"


class MonthlySnapshot(models.Model):
    """Month-end snapshot of the entire portfolio for growth tracking."""
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='portfolio_snapshots', null=True, blank=True,
    )
    month = models.DateField(
        help_text="First day of the month this snapshot represents",
    )
    data = models.JSONField(
        default=dict,
        help_text="Per-category breakdown: {category: {invested, current, returns}}",
    )
    total_invested = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_returns = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    money_added_this_month = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    returns_this_month = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-month']
        constraints = [
            models.UniqueConstraint(fields=['group', 'month'], name='unique_group_month_snapshot'),
        ]
        indexes = [
            Index(fields=['group', 'month']),
        ]

    def __str__(self):
        return f"Snapshot {self.month:%b %Y} — ₹{self.total_current_value:,.0f}"

    @property
    def return_pct(self):
        if self.total_invested:
            return (self.total_returns / self.total_invested * 100).quantize(Decimal('0.01'))
        return Decimal('0')


class RealEstateHolding(PnlMixin, models.Model):
    """
    Real Estate investment asset (Plot, Apartment, Commercial, Villa, Agricultural).
    Supports North Indian land units (Gaj / Sq. Yards) and structured metadata for LLM growth research.
    """
    PROPERTY_TYPE_CHOICES = (
        ('PLOT_LAND', 'Plot / Land'),
        ('APARTMENT_FLAT', 'Apartment / Flat'),
        ('COMMERCIAL', 'Commercial / Shop / Office'),
        ('VILLA_HOUSE', 'Villa / Independent House'),
        ('AGRICULTURAL', 'Agricultural Land'),
        ('OTHER', 'Other Real Estate'),
    )

    STATUS_CHOICES = (
        ('VACANT_PLOT', 'Vacant Plot / Land'),
        ('READY_SELF', 'Ready / Self-Use'),
        ('RENTED', 'Rented / Yield-Generating'),
        ('UNDER_CONSTRUCTION', 'Under Construction / Development'),
        ('RESALE_PLANNED', 'Held for Resale / Investment'),
    )

    AREA_UNIT_CHOICES = (
        ('GAJ', 'Gaj (Sq. Yards / 9 sq ft)'),
        ('SQFT', 'Square Feet (sq ft)'),
        ('SQYD', 'Square Yards (sq yd)'),
        ('ACRE', 'Acres'),
        ('BIGHA', 'Bigha'),
        ('SQMT', 'Square Meters (sq m)'),
    )

    ACQUISITION_TYPE_CHOICES = (
        ('PURCHASED', 'Purchased / Self-Acquired'),
        ('INHERITED', 'Inherited / Ancestral'),
        ('GIFTED', 'Gifted'),
    )

    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='real_estate_holdings', null=True, blank=True,
    )
    name = models.CharField(
        max_length=200,
        help_text="e.g. Golf City Sector 150 Plot B-42, ATS Greens Flat 302",
    )
    property_type = models.CharField(
        max_length=30, choices=PROPERTY_TYPE_CHOICES, default='PLOT_LAND',
    )
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default='VACANT_PLOT',
    )

    # Acquisition context (inheritance / gift / self-purchase)
    acquisition_type = models.CharField(
        max_length=20, choices=ACQUISITION_TYPE_CHOICES, default='PURCHASED',
        help_text="How this property was acquired (purchased, inherited, or gifted)",
    )
    original_owner = models.CharField(
        max_length=200, blank=True,
        help_text="Original owner for inherited/gifted properties (e.g. 'Late Shri R. K. Sharma, Father')",
    )
    inherited_year = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Year of inheritance/gift for tax holding period reference",
    )

    # Measurement (Explicit Gaj support)
    area_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Plot/Flat area in the selected unit (e.g. 200 Gaj, 1800 sq ft)",
    )
    area_unit = models.CharField(
        max_length=20, choices=AREA_UNIT_CHOICES, default='GAJ',
    )

    # Location Details (Structured for LLM Research)
    city = models.CharField(max_length=100, default='Noida')
    state = models.CharField(max_length=100, default='Uttar Pradesh')
    locality = models.CharField(
        max_length=200,
        help_text="e.g. Sector 150, Yamuna Expressway Sector 22D, Golf Course Ext Road",
    )
    landmark = models.CharField(
        max_length=255, blank=True,
        help_text="e.g. Near Jewar Airport link, 500m from Upcoming Metro Phase 4",
    )
    pincode = models.CharField(max_length=20, blank=True)
    google_maps_url = models.URLField(
        max_length=500, blank=True,
        help_text="Direct Google Maps pin / location URL",
    )
    micro_market_tag = models.CharField(
        max_length=150, blank=True,
        help_text="e.g. Yamuna Expressway Corridor, Dwarka Expressway, Sohna Road",
    )
    khasra_khata_number = models.CharField(
        max_length=100, blank=True,
        help_text="Legal registry / Khasra / Khatauni / Unit number",
    )

    # Financials & Valuation
    purchase_date = models.DateField(help_text="Date of purchase / registry agreement")
    purchase_price = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Base purchase consideration in INR",
    )
    stamp_duty_charges = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Registration, stamp duty, development & legal costs in INR",
    )
    current_valuation = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Latest estimated total market price in INR",
    )
    last_valuation_date = models.DateField(
        null=True, blank=True,
        help_text="Date of latest market price appraisal",
    )
    monthly_rental_income = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Monthly rental revenue in INR if rented out",
    )
    last_appreciated_fy = models.CharField(
        max_length=12, blank=True,
        help_text="FY whose year-end land appreciation has been applied (e.g. 'FY 2025-26')",
    )

    is_baby = models.BooleanField(
        default=False, help_text="Track in Child portfolio instead of master portfolio",
    )
    remarks = models.TextField(blank=True, help_text="Notes, registry details, builder info, etc.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-current_valuation', '-purchase_date']
        indexes = [
            Index(fields=['group', 'property_type']),
            Index(fields=['group', 'city']),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_property_type_display()}) — {self.locality}, {self.city}"

    @property
    def area_in_gaj(self) -> Decimal:
        """Normalized area in Gaj (1 Gaj = 1 Sq Yard = 9 Sq Ft = 0.836127 Sq M; 1 Acre = 4840 Gaj; 1 Bigha ~ 1008 Gaj)."""
        val = self.area_value or Decimal('0')
        u = self.area_unit
        if u in ('GAJ', 'SQYD'):
            return val
        elif u == 'SQFT':
            return (val / Decimal('9')).quantize(Decimal('0.01'))
        elif u == 'ACRE':
            return (val * Decimal('4840')).quantize(Decimal('0.01'))
        elif u == 'BIGHA':
            return (val * Decimal('1008')).quantize(Decimal('0.01'))
        elif u == 'SQMT':
            return (val * Decimal('1.19599')).quantize(Decimal('0.01'))
        return val

    @property
    def area_in_sqft(self) -> Decimal:
        """Normalized area in Square Feet."""
        val = self.area_value or Decimal('0')
        u = self.area_unit
        if u == 'SQFT':
            return val
        elif u in ('GAJ', 'SQYD'):
            return (val * Decimal('9')).quantize(Decimal('0.01'))
        elif u == 'ACRE':
            return (val * Decimal('43560')).quantize(Decimal('0.01'))
        elif u == 'BIGHA':
            return (val * Decimal('9072')).quantize(Decimal('0.01'))
        elif u == 'SQMT':
            return (val * Decimal('10.7639')).quantize(Decimal('0.01'))
        return val * Decimal('9')

    @property
    def area_display(self) -> str:
        """Formatted human readable display e.g. '200 Gaj (1,800 sq.ft)'."""
        if self.area_unit in ('GAJ', 'SQYD'):
            return f"{self.area_value:g} Gaj ({self.area_in_sqft:,.0f} sq.ft)"
        elif self.area_unit == 'SQFT':
            return f"{self.area_value:,.0f} sq.ft ({self.area_in_gaj:g} Gaj)"
        return f"{self.area_value:g} {self.get_area_unit_display()}"

    @property
    def total_cost_basis(self) -> Decimal:
        """Total invested amount: purchase price + stamp duty/registration/development."""
        return (self.purchase_price or Decimal('0')) + (self.stamp_duty_charges or Decimal('0'))

    @property
    def purchase_value(self) -> Decimal:
        """Alias for PnlMixin."""
        return self.total_cost_basis

    @property
    def current_value(self) -> Decimal:
        """Alias for PnlMixin."""
        return self.current_valuation or Decimal('0')

    @property
    def purchase_rate_per_gaj(self) -> Decimal:
        gaj = self.area_in_gaj
        if gaj and gaj > 0:
            return (self.purchase_price / gaj).quantize(Decimal('0.01'))
        return Decimal('0')

    @property
    def current_rate_per_gaj(self) -> Decimal:
        gaj = self.area_in_gaj
        if gaj and gaj > 0:
            return (self.current_valuation / gaj).quantize(Decimal('0.01'))
        return Decimal('0')

    @property
    def annual_rental_income(self) -> Decimal:
        return (self.monthly_rental_income or Decimal('0')) * Decimal('12')

    @property
    def rental_yield_pct(self) -> Decimal:
        if self.current_valuation and self.current_valuation > 0:
            return (self.annual_rental_income / self.current_valuation * 100).quantize(Decimal('0.01'))
        return Decimal('0')

    @property
    def cagr_pct(self) -> Decimal:
        """Annualized CAGR return % based on holding period."""
        if not self.purchase_date or not self.total_cost_basis or self.total_cost_basis <= 0 or not self.current_valuation:
            return Decimal('0')
        days = (date.today() - self.purchase_date).days
        if days <= 90:
            return Decimal('0')
        years = Decimal(str(days)) / Decimal('365.25')
        try:
            ratio = float(self.current_valuation / self.total_cost_basis)
            cagr = (ratio ** (1.0 / float(years)) - 1.0) * 100.0
            return Decimal(str(round(cagr, 2)))
        except Exception:
            return Decimal('0')

    @property
    def location_summary_for_llm(self) -> str:
        """Clean summary string for AI prompts."""
        parts = [self.locality, self.city, self.state]
        if self.landmark:
            parts.append(f"Landmark: {self.landmark}")
        if self.micro_market_tag:
            parts.append(f"Micro-market: {self.micro_market_tag}")
        if self.pincode:
            parts.append(f"PIN: {self.pincode}")
        return ", ".join(parts)

    def get_llm_research_prompt(self) -> str:
        """Generate ready-to-use LLM prompt for deep real estate market research."""
        acq_line = f"• Acquisition: {self.get_acquisition_type_display()}"
        if self.acquisition_type in ('INHERITED', 'GIFTED') and self.original_owner:
            acq_line += f" from {self.original_owner}"
        if self.inherited_year:
            acq_line += f" (year: {self.inherited_year})"
        acq_line += "\n"

        return (
            f"Please conduct a comprehensive real estate market research and valuation analysis for the following property:\n\n"
            f"• Property Name: {self.name}\n"
            f"• Type: {self.get_property_type_display()}\n"
            f"• Status: {self.get_status_display()}\n"
            f"{acq_line}"
            f"• Size: {self.area_display}\n"
            f"• Location: {self.location_summary_for_llm}\n"
            f"• Purchase Year/Date: {self.purchase_date.strftime('%B %Y')} (Purchased at ₹{self.purchase_price:,.0f} / ₹{self.purchase_rate_per_gaj:,.0f} per Gaj)\n"
            f"• Current Estimated Valuation: ₹{self.current_valuation:,.0f} (₹{self.current_rate_per_gaj:,.0f} per Gaj)\n\n"
            f"Please provide:\n"
            f"1. Current prevailing market price trends and circle rates in {self.locality}, {self.city}.\n"
            f"2. Major infrastructure catalysts, connectivity improvements (e.g. Metro, Expressways, Airport, Commercial hubs) impacting this micro-market.\n"
            f"3. Micro-market level supply-demand dynamics, absorption rates, and inventory overhang assessment.\n"
            f"4. 3-to-5 year capital appreciation outlook with growth potential analysis specific to this corridor/locality.\n"
            f"5. Rental yield outlook and comparison to the 2-4% Indian residential norm.\n"
            f"6. Key risks or supply overhangs in this specific sector/corridor.\n"
            f"7. Comparison of this property's CAGR against micro-market and city-level benchmarks."
        )

