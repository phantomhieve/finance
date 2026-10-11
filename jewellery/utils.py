"""Utilities for Jewellery photo processing, responsive thumbnail caching, and cleanup."""
import logging
import os
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

THUMBNAIL_SIZES = {
    'thumb': (480, 480),
    'full': (1600, 1600),
}

_SAFE_PHOTO_CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}


def get_or_create_thumbnail(original_path, size_variant='thumb', fallback_content_type='image/jpeg', force=False):
    """
    Return (file_path, content_type) for the requested size variant ('thumb' or 'full').
    Caches the resized WebP file under media/jewellery_photos/cache/<uuid>_<variant>.webp.
    If generation fails or the original cannot be decoded, falls back to original_path.
    """
    if not original_path or not os.path.exists(original_path):
        return original_path, fallback_content_type

    if size_variant not in THUMBNAIL_SIZES:
        size_variant = 'thumb'

    try:
        cache_dir = os.path.join(os.path.dirname(original_path), 'cache')
        os.makedirs(cache_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(original_path))[0]
        cached_path = os.path.join(cache_dir, f"{base_name}_{size_variant}.webp")

        orig_mtime = os.path.getmtime(original_path)
        if not force and os.path.exists(cached_path) and os.path.getmtime(cached_path) >= orig_mtime:
            return cached_path, 'image/webp'

        # Generate thumbnail
        with Image.open(original_path) as img:
            # Respect smartphone EXIF orientation before resizing
            img = ImageOps.exif_transpose(img)

            # Preserve transparency if RGBA/P, otherwise convert to RGB
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            max_size = THUMBNAIL_SIZES[size_variant]
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            temp_path = f"{cached_path}.tmp.{os.getpid()}"
            quality = 80 if size_variant == 'thumb' else 85
            img.save(temp_path, format='WEBP', quality=quality, method=4)
            os.replace(temp_path, cached_path)

        return cached_path, 'image/webp'
    except Exception as e:
        logger.warning("Failed to generate %s thumbnail for %s: %s", size_variant, original_path, e)
        return original_path, fallback_content_type


def delete_cached_thumbnails(original_path):
    """Clean up cached thumbnails when a jewellery photo is deleted or replaced."""
    if not original_path:
        return
    cache_dir = os.path.join(os.path.dirname(original_path), 'cache')
    base_name = os.path.splitext(os.path.basename(original_path))[0]
    for variant in ('thumb', 'full'):
        cached_path = os.path.join(cache_dir, f"{base_name}_{variant}.webp")
        try:
            if os.path.exists(cached_path):
                os.remove(cached_path)
        except OSError:
            pass
