import os
import logging
from django.core.management.base import BaseCommand
from jewellery.models import JewelleryItem
from jewellery.utils import get_or_create_thumbnail

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Pre-generate optimized WebP thumbnails (thumb & full) for jewellery items.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-generation of thumbnails even if already cached.',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        items = JewelleryItem.objects.exclude(photo='').exclude(photo__isnull=True)
        total_items = items.count()

        if total_items == 0:
            self.stdout.write(self.style.WARNING("No jewellery items with photos found."))
            return

        self.stdout.write(f"Processing {total_items} jewellery items (force={force})...")

        success_count = 0
        missing_count = 0
        error_count = 0

        for item in items:
            try:
                photo_path = item.photo.path
            except (ValueError, AttributeError):
                missing_count += 1
                continue

            if not os.path.exists(photo_path):
                self.stdout.write(self.style.WARNING(f"Item #{item.pk}: File not found ({photo_path})"))
                missing_count += 1
                continue

            try:
                # Generate both 'thumb' and 'full' variants
                thumb_path, _ = get_or_create_thumbnail(photo_path, size_variant='thumb', force=force)
                full_path, _ = get_or_create_thumbnail(photo_path, size_variant='full', force=force)

                orig_size = os.path.getsize(photo_path)
                thumb_size = os.path.getsize(thumb_path) if os.path.exists(thumb_path) else 0

                reduction = (1 - (thumb_size / orig_size)) * 100 if orig_size > 0 else 0
                self.stdout.write(
                    f"Item #{item.pk} ({item.display_label}): {orig_size / 1024:.1f} KB -> "
                    f"Thumb: {thumb_size / 1024:.1f} KB ({reduction:.1f}% reduction)"
                )
                success_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Item #{item.pk} failed: {e}"))
                error_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Processed: {total_items} | Succeeded: {success_count} | Missing files: {missing_count} | Errors: {error_count}"
        ))
