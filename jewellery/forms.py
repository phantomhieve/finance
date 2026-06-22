import os
import logging

from django import forms
from django.core.files.uploadedfile import UploadedFile
from pillow_heif import register_heif_opener

from .models import JewelleryItem

logger = logging.getLogger(__name__)
register_heif_opener()

# Upload hardening: cap size and restrict to a small set of raster image
# formats. We validate both the extension AND the real decoded format so a
# renamed/polyglot file can't slip through.
MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif'}
ALLOWED_PHOTO_FORMATS = {'JPEG', 'PNG', 'WEBP', 'GIF', 'HEIF'}


class JewelleryItemForm(forms.ModelForm):
    class Meta:
        model = JewelleryItem
        exclude = ['group', 'purchase_date', 'purchase_price', 'created_at', 'updated_at']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for optional in ('notes', 'purity', 'photo'):
            self.fields[optional].required = False

    def clean_weight_grams(self):
        """Coerce blank/None → 0 so the NOT NULL DB column is never sent NULL."""
        from decimal import Decimal
        val = self.cleaned_data.get('weight_grams')
        return val if val is not None else Decimal('0')

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
                'Unsupported file type. Upload a JPG, PNG, WEBP, GIF or HEIC image.'
            )

        # Decode with Pillow to confirm it is genuinely an image of an allowed
        # format (defends against polyglots and mislabelled extensions).
        # NOTE: Image.verify() must be called on a freshly opened image — it
        # consumes/corrupts the image object and must NOT be used after the
        # call (including accessing .format). Capture format first, then verify.
        try:
            from PIL import Image

            photo.seek(0)
            image = Image.open(photo)
            fmt = image.format          # capture BEFORE verify() destroys the object
            image.verify()              # raises if the file is not a valid image
        except Exception:
            raise forms.ValidationError('The uploaded file is not a valid image.')

        if fmt not in ALLOWED_PHOTO_FORMATS:
            raise forms.ValidationError('Unsupported image format.')

        # If it is HEIF/HEIC, convert it to standard JPEG so browsers can render it.
        if fmt == 'HEIF' or ext in ('.heic', '.heif'):
            from io import BytesIO
            from django.core.files.uploadedfile import InMemoryUploadedFile
            try:
                photo.seek(0)
                image = Image.open(photo)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                output = BytesIO()
                image.save(output, format='JPEG', quality=85)
                output.seek(0)
                
                new_filename = os.path.splitext(photo.name)[0] + '.jpg'
                new_photo = InMemoryUploadedFile(
                    file=output,
                    field_name='photo',
                    name=new_filename,
                    content_type='image/jpeg',
                    size=output.getbuffer().nbytes,
                    charset=None
                )
                return new_photo
            except Exception as e:
                logger.exception("Failed to convert HEIC to JPEG")
                raise forms.ValidationError("Could not process the iPhone photo format.")

        # verify() leaves the file pointer consumed — rewind so save() works.
        photo.seek(0)
        return photo
