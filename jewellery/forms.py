from django import forms
from .models import JewelleryItem

class JewelleryItemForm(forms.ModelForm):
    class Meta:
        model = JewelleryItem
        exclude = ['group', 'created_at', 'updated_at']
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_date'].required = False
        self.fields['purchase_price'].required = False
        self.fields['notes'].required = False
        self.fields['purity'].required = False
        self.fields['photo'].required = False
