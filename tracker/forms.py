from django import forms
from .models import Transaction, GoalIncrement, FinancialGoal, HRAExpense, MonthlyGoalAdjustment

ENTRY_TYPE_CHOICES = Transaction.TRANSACTION_TYPE_CHOICES

HRA_ENTRY_TYPE_CHOICES = HRAExpense.HRA_TYPE_CHOICES


class TransactionForm(forms.ModelForm):
    """Form for adding a monthly savings transaction."""

    type = forms.ChoiceField(
        choices=ENTRY_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Transaction
        fields = ['date', 'type', 'amount', 'remarks']
        widgets = {
            'date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
            ),
            'amount': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01', 'min': '0'},
            ),
            'remarks': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Optional note…'},
            ),
        }
        labels = {
            'amount': 'Amount (₹)',
            'remarks': 'Remarks',
        }


class GoalIncrementForm(forms.ModelForm):
    """Form for recording a step-up in monthly savings goal."""

    class Meta:
        model = GoalIncrement
        fields = ['effective_month', 'increment_amount', 'reason']
        widgets = {
            'effective_month': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
            ),
            'increment_amount': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. 5000', 'step': '0.01'},
            ),
            'reason': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'e.g. Annual salary hike',
                    'id': 'id_inc_reason',
                },
            ),
        }
        labels = {
            'effective_month': 'Effective From (1st of month)',
            'increment_amount': 'Increment Amount (+/- ₹)',
            'reason': 'Reason (optional)',
        }

class FinancialGoalForm(forms.ModelForm):
    """Form for creating or editing an annual financial goal for a specific FY."""

    fy_year = forms.IntegerField(
        label='Financial Year Start',
        min_value=2000,
        max_value=2099,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 2025 for FY 2025-26',
            'min': 2000, 'max': 2099,
        }),
        help_text='Enter the April start year (e.g. 2025 = FY 2025-26)',
    )

    class Meta:
        model = FinancialGoal
        fields = ['monthly_goal']
        widgets = {
            'monthly_goal': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01', 'min': '0'},
            ),
        }
        labels = {
            'monthly_goal': 'Base Monthly Goal (₹)',
        }


class MonthlyGoalAdjustmentForm(forms.ModelForm):
    """Form for applying a one-off adjustment to a specific month's goal."""

    class Meta:
        model = MonthlyGoalAdjustment
        fields = ['month', 'adjustment_amount', 'reason']
        widgets = {
            'month': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control'},
            ),
            'adjustment_amount': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. 20000 or -15000', 'step': '0.01'},
            ),
            'reason': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Optional reason (e.g. Vacation, bonus)',
                    'id': 'id_adj_reason',
                },
            ),
        }
        labels = {
            'month': 'Month (within this FY)',
            'adjustment_amount': 'Adjustment Amount (+/- ₹)',
            'reason': 'Reason (optional)',
        }

class HRAExpenseForm(forms.ModelForm):
    """Form to add an HRA transation."""
    type = forms.ChoiceField(
        choices=HRA_ENTRY_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Transaction Type'
    )

    class Meta:
        model = HRAExpense
        fields = ['date', 'amount', 'type', 'expense_type', 'mode_of_payment', 'remarks']
        widgets = {
            'date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control', 'required': True},
            ),
            'amount': forms.NumberInput(
                attrs={'class': 'form-control', 'placeholder': '0.00', 'step': '0.01', 'min': '0.01', 'required': True},
            ),
            'expense_type': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. Rent to Landlord', 'required': True},
            ),
            'mode_of_payment': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'e.g. UPI, Credit Card', 'list': 'mode-options'}
            ),
            'remarks': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Optional details'},
            ),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        entry_type = self.cleaned_data.get('type')
        instance.hra_type = entry_type
        # Maintain legacy behavior
        if entry_type in ['RENT_PAID', 'REVERT']:
            instance.is_revert = True
        else:
            instance.is_revert = False
        
        if commit:
            instance.save()
        return instance
