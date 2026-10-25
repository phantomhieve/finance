from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from . import crypto


class ExpenseCategory(models.Model):
    KIND_CHOICES = (
        ('SPEND', 'Spending'),
        ('TRANSFER', 'Transfer (excluded from spend)'),
        ('INCOME', 'Income / refund'),
    )

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='expense_categories')
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='SPEND')
    icon = models.CharField(max_length=40, default='category', help_text='Material Symbols icon name')
    hue = models.PositiveSmallIntegerField(default=230, help_text='0-360 colour hue for chips')
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Expense categories'
        constraints = [
            models.UniqueConstraint(fields=['group', 'name'], name='unique_expense_category_name'),
        ]

    def __str__(self):
        return self.name

    @property
    def counts_as_spend(self):
        return self.kind == 'SPEND'


class CategoryTemplate(models.Model):
    """System-wide category templates stored in the database to seed household categories."""

    name = models.CharField(max_length=60, unique=True)
    kind = models.CharField(max_length=10, choices=ExpenseCategory.KIND_CHOICES, default='SPEND')
    icon = models.CharField(max_length=40, default='category', help_text='Material Symbols icon name')
    hue = models.PositiveSmallIntegerField(default=230, help_text='0-360 colour hue for chips')
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'Category templates'

    def __str__(self):
        return self.name


class GmailAccount(models.Model):
    """A household member's Gmail mailbox connected with the gmail.readonly scope."""

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='gmail_accounts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gmail_accounts')
    email = models.EmailField()
    refresh_token_enc = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    backfill_days = models.PositiveSmallIntegerField(default=90)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_new = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['email']
        constraints = [
            models.UniqueConstraint(fields=['group', 'email'], name='unique_gmail_per_group'),
        ]

    def __str__(self):
        return self.email

    @property
    def refresh_token(self):
        return crypto.decrypt(self.refresh_token_enc)

    @refresh_token.setter
    def refresh_token(self, value):
        self.refresh_token_enc = crypto.encrypt(value)

    @property
    def needs_reconnect(self):
        return not self.is_active or not self.refresh_token


class PaymentSource(models.Model):
    """A bank account / card the household pays from. Auto-created when first seen in an email."""

    KIND_CHOICES = (
        ('CREDIT_CARD', 'Credit card'),
        ('DEBIT_CARD', 'Debit card'),
        ('BANK_ACCOUNT', 'Bank account'),
        ('UPI', 'UPI / wallet'),
        ('CASH', 'Cash'),
        ('OTHER', 'Other'),
    )
    KIND_ICONS = {
        'CREDIT_CARD': 'credit_card',
        'DEBIT_CARD': 'payment',
        'BANK_ACCOUNT': 'account_balance',
        'UPI': 'qr_code_2',
        'CASH': 'payments',
        'OTHER': 'wallet',
    }

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='payment_sources')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='OTHER')
    institution = models.CharField(max_length=60, blank=True)
    last4 = models.CharField(max_length=4, blank=True)
    nickname = models.CharField(max_length=60, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment_sources',
    )
    statement_password_enc = models.TextField(blank=True)
    is_auto = models.BooleanField(default=True, help_text='Created automatically from an email')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['institution', 'kind', 'last4']
        constraints = [
            models.UniqueConstraint(fields=['group', 'kind', 'institution', 'last4'], name='unique_payment_source'),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.nickname:
            return self.nickname
        parts = [self.institution or self.get_kind_display()]
        if self.institution:
            parts.append(self.get_kind_display().lower())
        if self.last4:
            parts.append(f'••{self.last4}')
        return ' '.join(parts)

    @property
    def short_name(self):
        """Compact label for dense lists, e.g. 'ICICI ••4402'."""
        if self.nickname:
            return self.nickname
        name = (self.institution or self.get_kind_display()).removesuffix(' Bank').removesuffix(' Card')
        return f'{name} ••{self.last4}' if self.last4 else name

    @property
    def icon(self):
        return self.KIND_ICONS.get(self.kind, 'wallet')

    @property
    def statement_password(self):
        return crypto.decrypt(self.statement_password_enc)

    @statement_password.setter
    def statement_password(self, value):
        self.statement_password_enc = crypto.encrypt(value)


class CardStatement(models.Model):
    STATUS_CHOICES = (
        ('BODY_ONLY', 'Totals from email'),
        ('PARSED', 'Line items parsed'),
        ('NEEDS_PASSWORD', 'PDF needs password'),
        ('FAILED', 'Could not read PDF'),
        ('DUPLICATE', 'Same statement already imported'),
    )

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='card_statements')
    payment_source = models.ForeignKey(PaymentSource, on_delete=models.CASCADE, related_name='statements')
    gmail_account = models.ForeignKey(GmailAccount, on_delete=models.SET_NULL, null=True, blank=True)
    gmail_message_id = models.CharField(max_length=64, blank=True)
    statement_date = models.DateField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_due = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='BODY_ONLY')
    pdf_blob = models.BinaryField(null=True, blank=True, editable=False,
                                  help_text='Original PDF (encrypted) kept until it is parsed, so a password can be added later')
    # SHA-256 of the original PDF bytes, so re-uploads / re-sent emails of the same file are recognised.
    pdf_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    duplicate_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    line_count = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    added_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reminder_sent_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-statement_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'gmail_message_id'], condition=~Q(gmail_message_id=''),
                name='unique_statement_message',
            ),
        ]

    def __str__(self):
        return f'{self.payment_source} statement {self.statement_date or self.created_at.date()}'


class Expense(models.Model):
    DIRECTION_CHOICES = (('DEBIT', 'Spent'), ('CREDIT', 'Received'))
    SOURCE_CHOICES = (
        ('EMAIL', 'Email alert'),
        ('STATEMENT', 'Card statement'),
        ('MANUAL', 'Added manually'),
    )
    CATEGORY_SOURCE_CHOICES = (
        ('USER', 'Set by you'),
        ('RULE', 'Learned rule'),
        ('AI', 'AI'),
        ('KEYWORD', 'Built-in keyword'),
        ('MATCH', 'Matched transfer'),
        ('NONE', 'Uncategorised'),
    )
    CHANNEL_CHOICES = (
        ('UPI', 'UPI'),
        ('CARD', 'Card'),
        ('NETBANKING', 'Net banking'),
        ('IMPS', 'IMPS / NEFT / RTGS'),
        ('ATM', 'ATM'),
        ('AUTO_DEBIT', 'Auto-debit'),
        ('CASH', 'Cash'),
        ('OTHER', 'Other'),
    )

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='expenses')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    direction = models.CharField(max_length=6, choices=DIRECTION_CHOICES, default='DEBIT')
    txn_date = models.DateField()
    txn_time = models.TimeField(null=True, blank=True)
    merchant = models.CharField(max_length=120, blank=True)
    merchant_raw = models.CharField(max_length=255, blank=True)
    merchant_key = models.CharField(max_length=60, blank=True, db_index=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    category_source = models.CharField(max_length=10, choices=CATEGORY_SOURCE_CHOICES, default='NONE')
    category_confidence = models.FloatField(null=True, blank=True)
    payment_source = models.ForeignKey(PaymentSource, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    channel = models.CharField(max_length=12, choices=CHANNEL_CHOICES, default='OTHER')
    reference = models.CharField(max_length=64, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='MANUAL')
    gmail_account = models.ForeignKey(GmailAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    gmail_message_id = models.CharField(max_length=64, blank=True)
    email_subject = models.CharField(max_length=255, blank=True)
    statement = models.ForeignKey(CardStatement, on_delete=models.SET_NULL, null=True, blank=True, related_name='added_expenses')
    # Stable identity for imported rows so re-syncs never duplicate them (blank for manual entries).
    dedupe_key = models.CharField(max_length=100, blank=True)

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses', help_text='Household member this spend belongs to',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    # Refunds & Returns linking
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    refund_date = models.DateField(null=True, blank=True)
    refund_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='refund_entries')

    # Credit Card EMI Tracking
    is_emi = models.BooleanField(default=False, db_index=True)
    emi_reference = models.CharField(max_length=64, blank=True)
    emi_installment_num = models.PositiveSmallIntegerField(null=True, blank=True)
    emi_total_installments = models.PositiveSmallIntegerField(null=True, blank=True)
    emi_component = models.CharField(max_length=16, blank=True)

    is_flagged = models.BooleanField(default=False)
    flag_reasons = models.JSONField(default=list, blank=True)
    flag_reviewed = models.BooleanField(default=False)
    # Soft delete: imported rows must stay as tombstones or the next sync would re-create them.
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-txn_date', '-txn_time', '-id']
        indexes = [
            models.Index(fields=['group', 'txn_date']),
            models.Index(fields=['group', 'merchant_key']),
            models.Index(fields=['group', 'is_emi']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'dedupe_key'], condition=~Q(dedupe_key=''),
                name='unique_expense_dedupe_key',
            ),
        ]

    def __str__(self):
        return f'{self.txn_date} {self.merchant or "—"} ₹{self.amount}'

    @property
    def is_refunded(self):
        return bool(self.refund_date or self.refunded_amount > 0 or self.refund_of_id)

    @property
    def is_fully_refunded(self):
        return self.direction == 'DEBIT' and self.amount > 0 and self.refunded_amount >= self.amount

    @property
    def net_amount(self):
        if self.direction == 'DEBIT':
            return max(Decimal('0.00'), self.amount - self.refunded_amount)
        return self.amount

    @property
    def is_spend(self):
        if self.direction != 'DEBIT':
            return False
        if self.refunded_amount >= self.amount and self.amount > 0:
            return False
        return self.category is None or self.category.kind == 'SPEND'

    @property
    def needs_review(self):
        return self.is_flagged and not self.flag_reviewed

    @property
    def icon(self):
        """Contextual Material Symbols icon: merchant brand icon → category icon → channel fallback."""
        from .parsing import brand_icon

        b_icon = brand_icon(self.merchant_key, f'{self.merchant} {self.merchant_raw}')
        if b_icon:
            return b_icon
        if self.category and self.category.icon:
            return self.category.icon
        if self.channel == 'ATM':
            return 'local_atm'
        if self.channel == 'UPI':
            return 'qr_code_2'
        if self.channel == 'CARD':
            return 'credit_card'
        return 'category'



class StatementLine(models.Model):
    statement = models.ForeignKey(CardStatement, on_delete=models.CASCADE, related_name='lines')
    txn_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_credit = models.BooleanField(default=False)
    matched_expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='statement_lines')
    was_added = models.BooleanField(default=False, help_text='No email alert matched — added from the statement')
    MATCH_METHOD_CHOICES = (
        ('', 'Not matched'),
        ('RULE', 'Amount + date rule'),
        ('AI', 'AI'),
        ('USER', 'Confirmed by you'),
        ('SKIP', 'Card payment (not spend)'),
    )
    match_method = models.CharField(max_length=4, choices=MATCH_METHOD_CHOICES, blank=True, default='')
    match_confidence = models.FloatField(null=True, blank=True)
    # Possible duplicate the matcher wasn't sure about — nothing is added until someone decides.
    needs_review = models.BooleanField(default=False)
    suggested_expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    match_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['txn_date', 'id']

    def __str__(self):
        return f'{self.txn_date} {self.description} {self.amount}'


class MerchantRule(models.Model):
    """Learned merchant → category mapping. USER rules come from edits and always win over AI."""

    SOURCE_CHOICES = (('USER', 'Taught by you'), ('AI', 'AI suggestion'))

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='merchant_rules')
    merchant_key = models.CharField(max_length=60)
    merchant_label = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='rules')
    source = models.CharField(max_length=4, choices=SOURCE_CHOICES, default='USER')
    hits = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['merchant_label', 'merchant_key']
        constraints = [
            models.UniqueConstraint(fields=['group', 'merchant_key'], name='unique_merchant_rule'),
        ]

    def __str__(self):
        return f'{self.merchant_label or self.merchant_key} → {self.category}'


class BrandKnowledge(models.Model):
    """Global merchant knowledge catalog that automatically expands via AI discovery.

    Stores normalized merchant keys, human-friendly display names, default category names,
    and specific Material Symbols icons.
    """
    SOURCE_CHOICES = (
        ('SEED', 'System Seed'),
        ('AI', 'AI Discovered'),
        ('USER', 'User Taught'),
    )

    merchant_key = models.CharField(max_length=60, unique=True, db_index=True)
    display_name = models.CharField(max_length=120)
    category_name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default='category', help_text='Material Symbols icon name')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='SEED')
    confidence = models.FloatField(default=1.0)
    hits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name', 'merchant_key']
        verbose_name_plural = 'Brand knowledge entries'

    def __str__(self):
        return f'{self.display_name} ({self.merchant_key}) → {self.category_name}'


class KeywordKnowledge(models.Model):
    """Global keyword mapping database table: substring token → category + icon."""

    keyword = models.CharField(max_length=40, unique=True, db_index=True)
    category_name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default='category', help_text='Material Symbols icon name')
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ['sort_order', 'keyword']
        verbose_name_plural = 'Keyword knowledge rules'

    def __str__(self):
        return f'{self.keyword} → {self.category_name}'


class ProcessedEmail(models.Model):
    """Every Gmail message we have looked at, so sync is idempotent (including ignored emails)."""

    KIND_CHOICES = (
        ('TXN', 'Transaction'),
        ('STATEMENT', 'Statement'),
        ('CARD_PAYMENT', 'Card payment'),
        ('IGNORED', 'Not a transaction'),
        ('ERROR', 'Failed to parse'),
    )

    gmail_account = models.ForeignKey(GmailAccount, on_delete=models.CASCADE, related_name='processed')
    message_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    subject = models.CharField(max_length=255, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['gmail_account', 'message_id'], name='unique_processed_email'),
        ]


class ExpenseAuditRun(models.Model):
    """Execution record for Gemini AI forensic anomaly scans with rate-limiting guardrails."""

    group = models.ForeignKey('tracker.AccountGroup', on_delete=models.CASCADE, related_name='expense_audit_runs')
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    expenses_scanned = models.PositiveIntegerField(default=0)
    anomalies_flagged = models.PositiveIntegerField(default=0)
    flagged_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['group', '-created_at']),
        ]

    def __str__(self):
        return f"{self.group.name} AI audit at {self.created_at:%Y-%m-%d %H:%M} ({self.anomalies_flagged} flagged)"
