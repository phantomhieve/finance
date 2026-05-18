from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User,
    AccountGroup,
    Category,
    Transaction,
    HRAExpense,
    FinancialGoal,
    GoalIncrement,
    MonthlyGoalAdjustment,
    WebAuthnCredential,
)


class AccountGroupForm(forms.ModelForm):
    new_portfolio_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text="Enter a new password to change it, or leave blank to keep the current one.",
        label="Portfolio Password",
    )

    class Meta:
        model = AccountGroup
        fields = ('name',)

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw = self.cleaned_data.get('new_portfolio_password')
        if raw:
            instance.set_portfolio_password(raw)
        if commit:
            instance.save()
        return instance


@admin.register(AccountGroup)
class AccountGroupAdmin(ModelAdmin):
    form = AccountGroupForm
    list_display = ('name', 'member_count', 'has_portfolio_password', 'created_at')
    search_fields = ('name',)

    @admin.display(boolean=True, description='Portfolio Password')
    def has_portfolio_password(self, obj):
        return bool(obj.portfolio_password)

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_member_count=Count('members'))

    @admin.display(description='Members')
    def member_count(self, obj):
        return obj._member_count


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin, ModelAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Vault Settings', {'fields': ('user_type', 'group')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'user_type', 'group', 'is_staff')
    list_filter = ('user_type', 'group', 'is_staff')


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'type', 'user')
    list_filter = ('type', 'user')
    search_fields = ('name',)


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(ModelAdmin):
    list_display = ('user', 'device_name', 'created_at')
    list_filter = ('user', 'created_at')
    list_select_related = ('user',)
    search_fields = ('device_name', 'user__username', 'user__email')
    ordering = ('-created_at',)
    readonly_fields = ('credential_id', 'public_key', 'sign_count', 'created_at')


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = ('date', 'user', 'amount', 'category', 'type')
    list_filter = ('user', 'type', 'date', 'category')
    search_fields = ('remarks',)


@admin.register(HRAExpense)
class HRAExpenseAdmin(ModelAdmin):
    list_display = ('date', 'user', 'amount', 'expense_type', 'hra_type', 'mode_of_payment')
    list_filter = ('user', 'hra_type', 'date', 'expense_type')
    search_fields = ('expense_type', 'remarks', 'mode_of_payment')


@admin.register(FinancialGoal)
class FinancialGoalAdmin(ModelAdmin):
    list_display = ('month', 'user', 'total_goal', 'monthly_goal')
    list_filter = ('user', 'month')


@admin.register(GoalIncrement)
class GoalIncrementAdmin(ModelAdmin):
    list_display = ('user', 'effective_month', 'increment_amount', 'reason', 'created_at')
    list_filter = ('user', 'effective_month')
    search_fields = ('reason',)


@admin.register(MonthlyGoalAdjustment)
class MonthlyGoalAdjustmentAdmin(ModelAdmin):
    list_display = ('user', 'month', 'adjustment_amount', 'reason', 'created_at')
    list_filter = ('user', 'month')
    search_fields = ('reason',)
