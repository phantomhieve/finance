from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    CardStatement, Expense, ExpenseCategory, GmailAccount, MerchantRule, PaymentSource, ProcessedEmail, StatementLine,
)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ModelAdmin):
    list_display = ('name', 'group', 'kind', 'icon', 'hue', 'sort_order')
    list_filter = ('kind', 'group')
    search_fields = ('name',)


@admin.register(GmailAccount)
class GmailAccountAdmin(ModelAdmin):
    list_display = ('email', 'user', 'group', 'is_active', 'last_synced_at', 'last_sync_new', 'connected_at')
    list_filter = ('is_active', 'group')
    search_fields = ('email',)
    exclude = ('refresh_token_enc',)
    readonly_fields = ('email', 'user', 'group', 'last_synced_at', 'last_sync_new', 'last_error', 'connected_at')


@admin.register(PaymentSource)
class PaymentSourceAdmin(ModelAdmin):
    list_display = ('__str__', 'group', 'kind', 'institution', 'last4', 'owner', 'is_auto', 'has_password')
    list_filter = ('kind', 'institution', 'group')
    exclude = ('statement_password_enc',)

    @admin.display(boolean=True, description='PDF password')
    def has_password(self, obj):
        return bool(obj.statement_password_enc)


class StatementLineInline(TabularInline):
    model = StatementLine
    extra = 0
    fields = ('txn_date', 'description', 'amount', 'is_credit', 'matched_expense', 'was_added')
    readonly_fields = fields
    can_delete = False


@admin.register(CardStatement)
class CardStatementAdmin(ModelAdmin):
    list_display = ('payment_source', 'statement_date', 'due_date', 'total_due', 'status',
                    'matched_count', 'added_count', 'is_paid')
    list_filter = ('status', 'is_paid', 'group')
    exclude = ('pdf_blob',)
    inlines = [StatementLineInline]


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ('txn_date', 'merchant', 'amount', 'direction', 'category', 'category_source',
                    'payment_source', 'member', 'source', 'is_flagged', 'is_deleted')
    list_filter = ('source', 'direction', 'category_source', 'is_flagged', 'is_deleted', 'category', 'group')
    search_fields = ('merchant', 'merchant_raw', 'notes', 'reference')
    date_hierarchy = 'txn_date'
    raw_id_fields = ('statement',)
    readonly_fields = ('gmail_account', 'gmail_message_id', 'email_subject', 'dedupe_key', 'merchant_key',
                       'created_by', 'created_at', 'updated_at')


@admin.register(MerchantRule)
class MerchantRuleAdmin(ModelAdmin):
    list_display = ('merchant_label', 'merchant_key', 'category', 'source', 'hits', 'group')
    list_filter = ('source', 'group')
    search_fields = ('merchant_key', 'merchant_label')


@admin.register(ProcessedEmail)
class ProcessedEmailAdmin(ModelAdmin):
    list_display = ('subject', 'kind', 'gmail_account', 'processed_at')
    list_filter = ('kind', 'gmail_account')
    search_fields = ('subject',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
