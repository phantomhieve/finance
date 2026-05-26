from django import forms
from .models import Transaction, GoalIncrement, FinancialGoal, HRAExpense, MonthlyGoalAdjustment, Note

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


class NoteForm(forms.ModelForm):
    """Form for creating / editing a personal note."""

    SECTION_CHOICES = [
        ('General', 'General'),
        ('Tax', 'Tax'),
        ('Reminder', 'Reminder'),
        ('Pending', 'Pending'),
    ]
    section = forms.ChoiceField(
        choices=SECTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_note_section'}),
        initial='General',
        label='Type',
    )

    pending_type = forms.ChoiceField(
        choices=[('', 'Select Type'), ('CREDIT', 'To Receive'), ('DEBIT', 'To Pay')],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_note_pending_type'}),
        required=False,
        label='Direction',
    )

    class Meta:
        model = Note
        fields = ['date', 'section', 'title', 'body', 'amount', 'pending_type', 'initial_amount', 'pending_amount']
        widgets = {
            'date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control', 'required': True, 'id': 'id_note_date'},
            ),
            'title': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Short title…',
                    'required': True,
                    'id': 'id_note_title',
                },
            ),
            'body': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Details, thoughts, reminders…',
                    'rows': 4,
                    'id': 'id_note_body',
                },
            ),
            'amount': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Optional amount (₹)',
                    'step': '0.01',
                    'min': '0',
                    'id': 'id_note_amount',
                },
            ),
            'initial_amount': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Initial amount (₹)',
                    'step': '0.01',
                    'min': '0',
                    'id': 'id_note_initial_amount',
                },
            ),
            'pending_amount': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Remaining (₹)',
                    'step': '0.01',
                    'min': '0',
                    'id': 'id_note_pending_amount',
                },
            ),
        }
        labels = {
            'title': 'Title',
            'body': 'Note',
            'amount': 'Amount (₹) — optional',
            'initial_amount': 'Initial Amount (₹)',
            'pending_amount': 'Remaining Pending (₹)',
        }

    def clean(self):
        cleaned_data = super().clean()
        section = cleaned_data.get('section')
        if section == 'Pending':
            pending_type = cleaned_data.get('pending_type')
            initial_amount = cleaned_data.get('initial_amount')
            pending_amount = cleaned_data.get('pending_amount')
            
            if not pending_type:
                self.add_error('pending_type', 'Direction (To Receive / To Pay) is required for Pending notes.')
            if initial_amount is None:
                self.add_error('initial_amount', 'Initial Amount is required for Pending notes.')
            elif initial_amount < 0:
                self.add_error('initial_amount', 'Initial Amount cannot be negative.')
                
            if pending_amount is None:
                self.add_error('pending_amount', 'Remaining Pending amount is required for Pending notes.')
            elif pending_amount < 0:
                self.add_error('pending_amount', 'Remaining Pending amount cannot be negative.')
            elif initial_amount is not None and pending_amount > initial_amount:
                self.add_error('pending_amount', 'Remaining Pending amount cannot exceed the Initial Amount.')
        return cleaned_data
