import os

from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import JewelleryItem

# Upload hardening: cap size and restrict to a small set of raster image
# formats. We validate both the extension AND the real decoded format so a
# renamed/polyglot file can't slip through.
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
ALLOWED_PHOTO_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF'}


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
        for optional in ('purchase_date', 'purchase_price', 'notes',
                         'purity', 'photo'):
            self.fields[optional].required = False

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        # Empty (None) or cleared (False) — nothing to validate.
        if not photo:
            return photo
        # Only validate freshly uploaded files; an unchanged edit re-submits the
        # already-stored FieldFile, which we trust.
        if not isinstance(photo, UploadedFile):
            return photo

        if photo.size > MAX_PHOTO_BYTES:
            raise forms.ValidationError('Image is too large (maximum 5 MB).')

        ext = os.path.splitext(photo.name or '')[1].lower()
        if ext not in ALLOWED_PHOTO_EXTENSIONS:
            raise forms.ValidationError(
                'Unsupported file type. Upload a JPG, PNG, WEBP or GIF image.'
            )

        # Decode with Pillow to confirm it is genuinely an image of an allowed
        # format (defends against polyglots and mislabelled extensions).
        try:
            from PIL import Image

            image = Image.open(photo)
            image.verify()
        except Exception:
            raise forms.ValidationError('The uploaded file is not a valid image.')

        if image.format not in ALLOWED_PHOTO_FORMATS:
            raise forms.ValidationError('Unsupported image format.')

        # verify() leaves the file pointer consumed — rewind so save() works.
        photo.seek(0)
        return photo
