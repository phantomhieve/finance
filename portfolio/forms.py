import datetime
from decimal import Decimal

from django import forms

from .models import (
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding, FinancialGoal,
    USStockHolding,
)


class EPFEntryForm(forms.ModelForm):
    class Meta:
        model = EPFEntry
        fields = ['date', 'entry_type', 'amount', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'entry_type': forms.Select(),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class NPSEntryForm(forms.ModelForm):
    class Meta:
        model = NPSEntry
        fields = ['date', 'contribution', 'interest_earned', 'total_balance', 'remarks']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'contribution': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'interest_earned': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'total_balance': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': 'Auto',
                'readonly': 'readonly',
                'style': 'opacity:0.6; cursor:not-allowed;',
            }),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._group = group

    def clean(self):
        """
        Always derive total_balance from previous entry + contribution + returns.
        total_balance = previous_row.total_balance + contribution + interest_earned
        User input for total_balance is ignored.
        """
        cleaned = super().clean()
        date = cleaned.get('date')
        contrib = cleaned.get('contribution') or Decimal('0')
        interest = cleaned.get('interest_earned') or Decimal('0')

        if date:
            group = self._group or getattr(self.instance, 'group', None)
            qs = NPSEntry.objects.all()
            if group:
                qs = qs.filter(group=group)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            prev = qs.filter(date__lte=date).order_by('-date', '-created_at').first()
            prev_balance = prev.total_balance if prev else Decimal('0')
            cleaned['total_balance'] = prev_balance + contrib + interest

        return cleaned


class FixedDepositForm(forms.ModelForm):
    class Meta:
        model = FixedDeposit
        fields = [
            'name', 'account_name', 'principal', 'interest_rate',
            'compounding', 'start_date', 'maturity_date', 'is_active', 'remarks',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. SBI FD'}),
            'account_name': forms.TextInput(attrs={'placeholder': 'e.g. Atul Acc'}),
            'principal': forms.NumberInput(attrs={'step': '0.01'}),
            'interest_rate': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '7.00'}),
            'compounding': forms.Select(),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'maturity_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class CashPositionForm(forms.ModelForm):
    class Meta:
        model = CashPosition
        fields = ['name', 'amount', 'remarks']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Kanika Acc'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class BondHoldingForm(forms.ModelForm):
    class Meta:
        model = BondHolding
        fields = ['account_name', 'amount', 'remarks']
        widgets = {
            'account_name': forms.TextInput(attrs={'placeholder': 'e.g. Kanika Acc'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class CryptoHoldingForm(forms.ModelForm):
    class Meta:
        model = CryptoHolding
        fields = ['name', 'amount_invested', 'current_value', 'remarks']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Bitcoin, Crypto'}),
            'amount_invested': forms.NumberInput(attrs={'step': '0.01'}),
            'current_value': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class CommodityHoldingForm(forms.ModelForm):
    class Meta:
        model = CommodityHolding
        fields = ['commodity_type', 'description', 'purity', 'weight_grams', 'purchase_price_per_gram']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'e.g. 20gm Coin - 1 (24k)'}),
            'purity': forms.Select(),
            'weight_grams': forms.NumberInput(attrs={'step': '0.01'}),
            'purchase_price_per_gram': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'e.g. 6500'}),
        }


class USStockHoldingForm(forms.ModelForm):
    class Meta:
        model = USStockHolding
        fields = [
            'symbol', 'company_name', 'quantity', 'vest_date',
            'purchase_price_usd', 'purchase_usd_inr', 'remarks',
        ]
        widgets = {
            'symbol': forms.TextInput(attrs={'placeholder': 'UBER', 'value': 'UBER'}),
            'company_name': forms.TextInput(attrs={'placeholder': 'Uber Technologies', 'value': 'Uber Technologies'}),
            'quantity': forms.NumberInput(attrs={'placeholder': 'Number of shares', 'min': '1'}),
            'vest_date': forms.DateInput(attrs={'type': 'date', 'value': datetime.date.today().isoformat()}),
            'purchase_price_usd': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Auto-fetched if blank',
            }),
            'purchase_usd_inr': forms.NumberInput(attrs={
                'step': '0.01', 'placeholder': 'Auto-fetched if blank',
            }),
            'remarks': forms.TextInput(attrs={'placeholder': 'e.g. Q1 2026 RSU vest'}),
        }

    def clean_purchase_price_usd(self):
        val = self.cleaned_data.get('purchase_price_usd')
        if val is None:
            return Decimal('0')
        return val

    def clean_purchase_usd_inr(self):
        val = self.cleaned_data.get('purchase_usd_inr')
        if val is None:
            return Decimal('0')
        return val


class FinancialGoalForm(forms.ModelForm):
    class Meta:
        model = FinancialGoal
        fields = ['label', 'target_amount', 'sort_order']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g. 50L, 1Cr'}),
            'target_amount': forms.NumberInput(attrs={'step': '1', 'placeholder': '5000000'}),
            'sort_order': forms.NumberInput(attrs={'placeholder': '0'}),
        }
