from django import forms

from .models import Expense, ExpenseCategory, PaymentSource

MAX_STATEMENT_BYTES = 10 * 1024 * 1024


class ExpenseForm(forms.ModelForm):
    remember = forms.BooleanField(required=False, initial=False)
    is_emi = forms.BooleanField(required=False, initial=False)

    class Meta:
        model = Expense
        fields = ['amount', 'direction', 'txn_date', 'merchant', 'category', 'payment_source', 'member', 'notes', 'is_emi']
        widgets = {'txn_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExpenseCategory.objects.filter(group=group)
        self.fields['payment_source'].queryset = PaymentSource.objects.filter(group=group)
        self.fields['member'].queryset = group.members.all() if group else self.fields['member'].queryset.none()
        for name in ('category', 'payment_source', 'member', 'notes', 'is_emi'):
            self.fields[name].required = False
        self.fields['merchant'].required = True

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount is None or amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        return amount


class CategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ['name', 'kind', 'icon', 'hue']

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self.fields['icon'].required = False
        self.fields['hue'].required = False

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        clash = ExpenseCategory.objects.filter(group=self.group, name__iexact=name)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('A category with this name already exists.')
        return name

    def clean_icon(self):
        icon = (self.cleaned_data.get('icon') or '').strip().lower()
        return icon if icon.replace('_', '').isalnum() else 'category'

    def clean_hue(self):
        hue = self.cleaned_data.get('hue')
        return 230 if hue is None else max(0, min(360, hue))


class PaymentSourceForm(forms.ModelForm):
    statement_password = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False, attrs={'autocomplete': 'new-password'}),
        help_text='Used to open password-protected statement PDFs. Leave blank to keep the saved one.',
    )
    clear_password = forms.BooleanField(required=False)

    class Meta:
        model = PaymentSource
        fields = ['nickname', 'kind', 'institution', 'last4', 'owner']

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['owner'].queryset = group.members.all() if group else self.fields['owner'].queryset.none()
        self.fields['owner'].required = False

    def clean_last4(self):
        last4 = (self.cleaned_data.get('last4') or '').strip()
        if last4 and (not last4.isdigit() or len(last4) != 4):
            raise forms.ValidationError('Enter the last 4 digits.')
        return last4

    def save(self, commit=True):
        source = super().save(commit=False)
        if self.cleaned_data.get('clear_password'):
            source.statement_password = ''
        elif self.cleaned_data.get('statement_password'):
            source.statement_password = self.cleaned_data['statement_password']
        if commit:
            source.save()
        return source


class StatementUploadForm(forms.Form):
    payment_source = forms.ModelChoiceField(queryset=PaymentSource.objects.none())
    pdf = forms.FileField()
    password = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'autocomplete': 'off'}))
    save_password = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_source'].queryset = PaymentSource.objects.filter(group=group, kind='CREDIT_CARD')

    def clean_pdf(self):
        pdf = self.cleaned_data['pdf']
        if pdf.size > MAX_STATEMENT_BYTES:
            raise forms.ValidationError('PDF is too large (maximum 10 MB).')
        head = pdf.read(5)
        pdf.seek(0)
        if head != b'%PDF-':
            raise forms.ValidationError('Upload the statement as a PDF file.')
        return pdf
