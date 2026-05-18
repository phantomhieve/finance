from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    ZerodhaAccount, StockHolding, MutualFundHolding,
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding,
    CommodityPrice, MonthlySnapshot, FinancialGoal,
    PortfolioInsight, USStockHolding,
    InsightGenerationSettings,
)


@admin.register(ZerodhaAccount)
class ZerodhaAccountAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'group', 'last_synced')
    list_filter = ('group',)
    list_select_related = ('group',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(StockHolding)
class StockHoldingAdmin(ModelAdmin):
    list_display = ('symbol', 'account', 'quantity', 'purchase_value', 'current_value')
    list_filter = ('account',)
    list_select_related = ('account',)
    search_fields = ('symbol',)


@admin.register(MutualFundHolding)
class MutualFundHoldingAdmin(ModelAdmin):
    list_display = ('fund_name_short', 'fund_type', 'account', 'units', 'purchase_value', 'current_value')
    list_filter = ('fund_type', 'account')
    list_select_related = ('account',)
    search_fields = ('fund_name',)

    @admin.display(description='Fund')
    def fund_name_short(self, obj):
        return (obj.fund_name or '')[:60]


@admin.register(EPFEntry)
class EPFEntryAdmin(ModelAdmin):
    list_display = ('date', 'entry_type', 'amount', 'group', 'remarks')
    list_filter = ('entry_type', 'group')
    list_select_related = ('group',)
    ordering = ('-date',)


@admin.register(NPSEntry)
class NPSEntryAdmin(ModelAdmin):
    list_display = ('date', 'group', 'contribution', 'interest_earned', 'total_balance', 'remarks')
    list_filter = ('group',)
    list_select_related = ('group',)
    ordering = ('-date',)


@admin.register(FixedDeposit)
class FixedDepositAdmin(ModelAdmin):
    list_display = ('name', 'group', 'account_name', 'principal', 'interest_rate', 'compounding', 'start_date', 'maturity_date', 'is_active')
    list_filter = ('is_active', 'compounding', 'group', 'account_name')
    list_select_related = ('group',)
    search_fields = ('name', 'account_name')


@admin.register(CashPosition)
class CashPositionAdmin(ModelAdmin):
    list_display = ('name', 'group', 'amount', 'remarks')
    list_filter = ('group',)
    list_select_related = ('group',)
    search_fields = ('name',)


@admin.register(BondHolding)
class BondHoldingAdmin(ModelAdmin):
    list_display = ('account_name', 'group', 'amount', 'remarks')
    list_filter = ('group',)
    list_select_related = ('group',)


@admin.register(CryptoHolding)
class CryptoHoldingAdmin(ModelAdmin):
    list_display = ('name', 'group', 'amount_invested', 'current_value', 'remarks')
    list_filter = ('group',)
    list_select_related = ('group',)


@admin.register(CommodityHolding)
class CommodityHoldingAdmin(ModelAdmin):
    list_display = ('commodity_type', 'group', 'description', 'purity', 'weight_grams')
    list_filter = ('commodity_type', 'group')
    list_select_related = ('group',)


@admin.register(CommodityPrice)
class CommodityPriceAdmin(ModelAdmin):
    list_display = ('commodity_type', 'rate_per_gram', 'fetched_at')
    list_filter = ('commodity_type',)


@admin.register(MonthlySnapshot)
class MonthlySnapshotAdmin(ModelAdmin):
    list_display = ('month', 'group', 'total_current_value', 'total_invested', 'total_returns', 'money_added_this_month', 'returns_this_month')
    list_filter = ('group',)
    list_select_related = ('group',)
    ordering = ('-month',)


@admin.register(FinancialGoal)
class FinancialGoalAdmin(ModelAdmin):
    list_display = ('label', 'group', 'target_amount', 'sort_order')
    list_filter = ('group',)
    list_select_related = ('group',)
    ordering = ('sort_order',)


@admin.register(USStockHolding)
class USStockHoldingAdmin(ModelAdmin):
    list_display = ('symbol', 'company_name', 'quantity', 'vest_date', 'purchase_price_usd', 'current_price_usd', 'current_usd_inr', 'last_refreshed')
    list_filter = ('symbol', 'group')
    list_select_related = ('group',)
    search_fields = ('symbol', 'company_name')
    ordering = ('-vest_date',)


@admin.register(InsightGenerationSettings)
class InsightGenerationSettingsAdmin(ModelAdmin):
    list_display = ('cooldown_days', 'updated_at')
    fields = ('cooldown_days', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not InsightGenerationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PortfolioInsight)
class PortfolioInsightAdmin(ModelAdmin):
    list_display = ('generated_at', 'group', 'model_used')
    list_filter = ('group',)
    list_select_related = ('group',)
    ordering = ('-generated_at',)
    readonly_fields = ('generated_at', 'model_used', 'prompt_data', 'insights')
