import datetime
from decimal import Decimal

from django import forms

from pftracker.utils import fy_label, fy_start_from_label, fy_start_year

from .models import (
    EPFEntry, NPSEntry, FixedDeposit, CashPosition,
    BondHolding, CryptoHolding, CommodityHolding, FinancialGoal,
    USStockHolding, RealEstateHolding,
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
            'compounding', 'start_date', 'maturity_date', 'is_active', 'is_baby', 'remarks',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. SBI FD'}),
            'account_name': forms.TextInput(attrs={'placeholder': 'e.g. Primary Acc'}),
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
        fields = ['name', 'amount', 'is_baby', 'remarks']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Secondary Acc'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class BondHoldingForm(forms.ModelForm):
    class Meta:
        model = BondHolding
        fields = ['account_name', 'amount', 'is_baby', 'remarks']
        widgets = {
            'account_name': forms.TextInput(attrs={'placeholder': 'e.g. Secondary Acc'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class CryptoHoldingForm(forms.ModelForm):
    class Meta:
        model = CryptoHolding
        fields = ['name', 'amount_invested', 'current_value', 'is_baby', 'remarks']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Bitcoin, Crypto'}),
            'amount_invested': forms.NumberInput(attrs={'step': '0.01'}),
            'current_value': forms.NumberInput(attrs={'step': '0.01'}),
            'remarks': forms.TextInput(attrs={'placeholder': 'Optional'}),
        }


class CommodityHoldingForm(forms.ModelForm):
    class Meta:
        model = CommodityHolding
        fields = ['commodity_type', 'description', 'purity', 'weight_grams', 'purchase_price_per_gram', 'is_baby']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'e.g. 20gm Coin - 1 (24k)'}),
            'purity': forms.Select(),
            'weight_grams': forms.NumberInput(attrs={'step': '0.01'}),
            'purchase_price_per_gram': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'e.g. 6500'}),
        }

    def clean_purchase_price_per_gram(self):
        val = self.cleaned_data.get('purchase_price_per_gram')
        if val is None or val <= 0:
            raise forms.ValidationError("Purchase price per gram must be greater than 0.")
        return val

    def clean_weight_grams(self):
        val = self.cleaned_data.get('weight_grams')
        if val is None or val <= 0:
            raise forms.ValidationError("Weight in grams must be greater than 0.")
        return val



class USStockHoldingForm(forms.ModelForm):
    class Meta:
        model = USStockHolding
        fields = [
            'symbol', 'company_name', 'quantity', 'vest_date',
            'purchase_price_usd', 'purchase_usd_inr', 'is_baby', 'remarks',
        ]
        widgets = {
            'symbol': forms.TextInput(attrs={'placeholder': 'UBER', 'value': 'UBER'}),
            'company_name': forms.TextInput(attrs={'placeholder': 'e.g. Employer Corp'}),
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


def _fy_choices(today=None):
    """Rolling FY dropdown: two closed years for back-filling, current, five ahead, long term."""
    cur = fy_start_year(today)
    choices = [('', '— Select financial year —')]
    for start in range(cur - 2, cur + 6):
        label = fy_label(start)
        if start < cur:
            hint = 'closed'
        elif start == cur:
            hint = f'current · ends 31 Mar {start + 1}'
        else:
            hint = f'ends 31 Mar {start + 1}'
        choices.append((label, f'{label} ({hint})'))
    choices.append((FinancialGoal.LONG_TERM, 'Long term / custom horizon'))
    return choices


class FinancialGoalForm(forms.ModelForm):
    financial_year = forms.CharField(max_length=30, required=False, widget=forms.Select())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['financial_year'].widget.choices = _fy_choices()

    def clean_financial_year(self):
        value = (self.cleaned_data.get('financial_year') or '').strip()
        if value and value != FinancialGoal.LONG_TERM and fy_start_from_label(value) is None:
            raise forms.ValidationError('Use the format "FY 2026-27" or "Long Term".')
        return value

    def save(self, commit=True):
        if {'financial_year', 'target_date'} & set(self.changed_data):
            self.instance.closing_value = None
        return super().save(commit=commit)

    class Meta:
        model = FinancialGoal
        fields = ['financial_year', 'label', 'target_amount', 'target_date', 'notes']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'e.g. FY 2026-27 Target'}),
            'target_amount': forms.NumberInput(attrs={'step': '1', 'placeholder': '45000000'}),
            'target_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Strategic plan, allocation notes…'}),
        }


class RealEstateHoldingForm(forms.ModelForm):
    class Meta:
        model = RealEstateHolding
        fields = [
            'name', 'property_type', 'status',
            'acquisition_type', 'original_owner', 'inherited_year',
            'area_value', 'area_unit',
            'locality', 'city', 'state', 'landmark', 'pincode',
            'micro_market_tag', 'google_maps_url', 'khasra_khata_number',
            'purchase_date', 'purchase_price', 'stamp_duty_charges',
            'current_valuation', 'last_valuation_date', 'monthly_rental_income',
            'is_baby', 'remarks',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Sector 150 Express Plot B-42'}),
            'property_type': forms.Select(),
            'status': forms.Select(),
            'acquisition_type': forms.Select(),
            'original_owner': forms.TextInput(attrs={'placeholder': 'e.g. Late Shri Ram Khetan, Father'}),
            'inherited_year': forms.NumberInput(attrs={'placeholder': 'e.g. 2015'}),
            'area_value': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'e.g. 200'}),
            'area_unit': forms.Select(),
            'locality': forms.TextInput(attrs={'placeholder': 'e.g. Sector 150, Express Corridor'}),
            'city': forms.TextInput(attrs={'placeholder': 'e.g. Noida'}),
            'state': forms.TextInput(attrs={'placeholder': 'e.g. Uttar Pradesh'}),
            'landmark': forms.TextInput(attrs={'placeholder': 'e.g. Near Jewar Airport link / Sports City'}),
            'pincode': forms.TextInput(attrs={'placeholder': 'e.g. 201310'}),
            'micro_market_tag': forms.TextInput(attrs={'placeholder': 'e.g. Noida Expressway / Yamuna Expressway Corridor'}),
            'google_maps_url': forms.URLInput(attrs={'placeholder': 'https://maps.app.goo.gl/...'}),
            'khasra_khata_number': forms.TextInput(attrs={'placeholder': 'e.g. Khasra 412/1, Registry Doc #889'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'purchase_price': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Base purchase price in ₹'}),
            'stamp_duty_charges': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Stamp duty & registry fees in ₹'}),
            'current_valuation': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Current market price estimate in ₹'}),
            'last_valuation_date': forms.DateInput(attrs={'type': 'date'}),
            'monthly_rental_income': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'remarks': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Registry notes, builder info, tenant details...'}),
        }

    def clean_purchase_price(self):
        val = self.cleaned_data.get('purchase_price')
        if val is None or val < 0:
            raise forms.ValidationError("Purchase price must be zero or positive.")
        return val

    def clean_current_valuation(self):
        val = self.cleaned_data.get('current_valuation')
        if val is None or val < 0:
            raise forms.ValidationError("Current valuation must be zero or positive.")
        return val

    def clean_area_value(self):
        val = self.cleaned_data.get('area_value')
        if val is None or val <= 0:
            raise forms.ValidationError("Area value must be greater than zero.")
        return val


class RealEstateValuationForm(forms.ModelForm):
    class Meta:
        model = RealEstateHolding
        fields = ['current_valuation', 'last_valuation_date', 'monthly_rental_income', 'remarks']
        widgets = {
            'current_valuation': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Updated market price in ₹'}),
            'last_valuation_date': forms.DateInput(attrs={'type': 'date', 'value': datetime.date.today().isoformat()}),
            'monthly_rental_income': forms.NumberInput(attrs={'step': '0.01', 'placeholder': '0.00'}),
            'remarks': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Reason for price update / market research notes...'}),
        }

