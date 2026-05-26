from django.db import models
from django.db.models import Index
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import check_password, make_password


class AccountGroup(models.Model):
    name = models.CharField(max_length=100)
    portfolio_password = models.CharField(
        max_length=256, blank=True, default='',
        help_text="Hashed password to access portfolio for this group.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def set_portfolio_password(self, raw_password):
        if raw_password:
            self.portfolio_password = make_password(raw_password)
        else:
            self.portfolio_password = ''

    def check_portfolio_password(self, raw_password):
        if not self.portfolio_password:
            return False
        return check_password(raw_password, self.portfolio_password)


class User(AbstractUser):
    USER_TYPES = (
        ('PRIMARY', 'Primary Account Holder'),
        ('ACCOUNT_HOLDER', 'Account Holder'),
        ('LANDLORD', 'Landlord'),
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='PRIMARY')
    group = models.ForeignKey(
        AccountGroup, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='members',
    )

    def __str__(self):
        return self.username

    @property
    def _is_account_member(self):
        return self.user_type in ('PRIMARY', 'ACCOUNT_HOLDER')

    can_edit_savings = _is_account_member
    can_view_savings = _is_account_member
    can_edit_hra = _is_account_member

    @property
    def can_view_hra(self):
        return True

    @property
    def can_view_portfolio(self):
        return self.user_type == 'PRIMARY'


class WebAuthnCredential(models.Model):
    """Stores a WebAuthn (FaceID/TouchID/fingerprint) credential for portfolio unlock."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webauthn_credentials')
    credential_id = models.BinaryField(unique=True)
    public_key = models.BinaryField()
    sign_count = models.PositiveIntegerField(default=0)
    device_name = models.CharField(max_length=100, default='Device')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.device_name}"


class Category(models.Model):
    TYPE_CHOICES = (
        ('INCOME', 'Income'),
        ('SAVINGS', 'Savings'),
        ('TRANSFER', 'Transfer'),
        ('EXPENSE', 'Expense'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('SAVINGS', 'Savings'),
        ('TRANSFER', 'Transfer'),
        ('EXTRA_INCOME', 'Extra Income'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['user', 'date']),
            Index(fields=['user', 'type', 'date']),
        ]

    def __str__(self):
        return f"{self.date} - {self.amount} - {self.category.name if self.category else self.type}"


class HRAExpense(models.Model):
    HRA_TYPE_CHOICES = (
        ('RENT_PAID', 'Rent Paid'),
        ('EXPENSE', 'Expense'),
        ('REVERT', 'Revert'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hra_expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    expense_type = models.CharField(max_length=100)
    remarks = models.CharField(max_length=255, blank=True)
    mode_of_payment = models.CharField(max_length=100, blank=True)
    hra_type = models.CharField(max_length=20, choices=HRA_TYPE_CHOICES, default='EXPENSE')
    is_revert = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['user', 'date']),
            Index(fields=['user', 'hra_type', 'date']),
        ]

    def __str__(self):
        return f"HRA: {self.date} - {self.amount} - {self.expense_type}"


class FinancialGoal(models.Model):
    """Monthly savings goal per FY (distinct from portfolio.FinancialGoal which tracks portfolio milestones)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='goals')
    month = models.DateField()
    total_goal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    monthly_goal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    increment = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"Goals for {self.month.strftime('%Y-%m')} ({self.user.username})"


class GoalIncrement(models.Model):
    """Records a step-up (or step-down) in the monthly savings goal from a given month onwards."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='goal_increments')
    effective_month = models.DateField(
        help_text="The first month this new monthly goal applies to (format: YYYY-MM-01)."
    )
    increment_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Amount to add (or subtract) to the base monthly goal from this month onwards."
    )
    reason = models.CharField(max_length=200, blank=True,
        help_text="Optional: reason for this change (e.g. 'salary hike')")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['effective_month']

    def __str__(self):
        return (f"{self.user.username}: +₹{self.increment_amount:,} "
                f"from {self.effective_month.strftime('%b %Y')}")


class MonthlyGoalAdjustment(models.Model):
    """
    A one-off adjustment to the monthly goal for a specific month.
    Unlike GoalIncrement, this only affects that single month.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='goal_adjustments')
    month = models.DateField(
        help_text="Month this adjustment applies to (format: YYYY-MM-01)."
    )
    adjustment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Amount to add (or subtract) to this month's goal only.",
    )
    reason = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional: reason for this one-off change (e.g. 'bonus', 'vacation').",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['month']
        constraints = [
            models.UniqueConstraint(fields=['user', 'month'], name='unique_user_month_adjustment'),
        ]

    def __str__(self):
        return (
            f"{self.user.username}: adj {self.adjustment_amount} "
            f"for {self.month.strftime('%b %Y')}"
        )


class Note(models.Model):
    """A personal note — user-scoped, with an optional section tag, amount, and financial year."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notes')
    date = models.DateField()
    financial_year = models.IntegerField(
        null=True, blank=True,
        help_text="Start year of the financial year (e.g. 2025 for FY 2025-26)",
    )
    section = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Free-text section/tag, e.g. 'Savings', 'Tax', 'Goal'",
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default='')
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text='Optional linked amount (₹)',
    )
    
    # Extra fields for Pending notes
    pending_type = models.CharField(
        max_length=10,
        choices=[('CREDIT', 'To Receive'), ('DEBIT', 'To Pay')],
        blank=True,
        default='',
    )
    initial_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
    )
    pending_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            Index(fields=['user', '-date']),
            Index(fields=['user', 'section']),
            Index(fields=['user', 'financial_year']),
        ]

    def save(self, *args, **kwargs):
        if self.date and self.financial_year is None:
            self.financial_year = self.date.year if self.date.month >= 4 else self.date.year - 1
        super().save(*args, **kwargs)

    def __str__(self):
        section_str = f'[{self.section}] ' if self.section else ''
        return f"{section_str}{self.title} ({self.date})"

