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

    @property
    def total_stocks_value(self):
        return self.stock_holdings.aggregate(t=models.Sum('current_value'))['t'] or Decimal('0')

    @property
    def total_index_mf_value(self):
        return self.mf_holdings.filter(fund_type='INDEX').aggregate(
            t=models.Sum('current_value'))['t'] or Decimal('0')

    @property
    def total_other_mf_value(self):
        return self.mf_holdings.filter(fund_type='OTHER').aggregate(
            t=models.Sum('current_value'))['t'] or Decimal('0')

    @property
    def total_value(self):
        return self.total_stocks_value + self.total_index_mf_value + self.total_other_mf_value


class StockHolding(PnlMixin, models.Model):
    account = models.ForeignKey(
        ZerodhaAccount, on_delete=models.CASCADE, related_name='stock_holdings',
    )
    symbol = models.CharField(max_length=50)
    quantity = models.IntegerField(default=0)
    purchase_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)

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

    class Meta:
        ordering = ['fund_name']
        indexes = [
            Index(fields=['account', 'fund_type']),
        ]

    def __str__(self):
        return f"{self.account.name} — {self.fund_name[:60]}"


class FinancialGoal(models.Model):
    """Portfolio milestone goal (e.g. 50L, 1Cr). Distinct from tracker.FinancialGoal which tracks monthly savings."""
    group = models.ForeignKey(
        'tracker.AccountGroup', on_delete=models.CASCADE,
        related_name='portfolio_goals', null=True, blank=True,
    )
    label = models.CharField(max_length=50, help_text="e.g. 50L, 1Cr")
    target_amount = models.DecimalField(max_digits=14, decimal_places=0)
    sort_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'target_amount']

    def __str__(self):
        return f"{self.label} — ₹{self.target_amount:,.0f}"


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
    company_name = models.CharField(max_length=200, default='Uber Technologies')
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

    @property
    def current_price_inr(self):
        return (self.current_price_usd * self.current_usd_inr).quantize(Decimal('0.01'))

    @property
    def purchase_price_inr(self):
        return (self.purchase_price_usd * self.purchase_usd_inr).quantize(Decimal('0.01'))


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
