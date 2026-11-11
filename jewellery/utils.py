"""Utilities for Jewellery photo processing, responsive thumbnail caching, and cleanup."""
import logging
import os
from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def safe_media_path(path):
    """Return the resolved real path if it lies inside MEDIA_ROOT, else None.

    Guards every filesystem access derived from stored file names against path traversal
    (``..`` segments, absolute paths, symlinks leaving the media directory).
    """
    if not path:
        return None
    root = os.path.realpath(str(settings.MEDIA_ROOT))
    real = os.path.realpath(str(path))
    if real == root or not real.startswith(root + os.sep):
        return None
    return real

THUMBNAIL_SIZES = {
    'thumb': (480, 480),
    'full': (1600, 1600),
}
MAX_PHOTO_PIXELS = 40_000_000

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
    original_path = safe_media_path(original_path)
    if not original_path or not os.path.exists(original_path):
        return original_path, fallback_content_type

    if size_variant not in THUMBNAIL_SIZES:
        size_variant = 'thumb'

    try:
        cache_dir = os.path.join(os.path.dirname(original_path), 'cache')
        os.makedirs(cache_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(original_path))[0]
        base_name = "".join(c for c in base_name if c.isalnum() or c in ('-', '_'))
        if not base_name:
            return original_path, fallback_content_type

        cached_path = safe_media_path(os.path.join(cache_dir, f"{base_name}_{size_variant}.webp"))
        if not cached_path:
            return original_path, fallback_content_type

        orig_mtime = os.path.getmtime(original_path)
        if not force and os.path.exists(cached_path) and os.path.getmtime(cached_path) >= orig_mtime:
            return cached_path, 'image/webp'

        # Generate thumbnail
        with Image.open(original_path) as img:
            if img.width <= 0 or img.height <= 0 or (img.width * img.height) > MAX_PHOTO_PIXELS:
                raise ValueError("Image dimensions exceed safety limit")
            # Respect smartphone EXIF orientation before resizing
            img = ImageOps.exif_transpose(img)

            # Preserve transparency if RGBA/P, otherwise convert to RGB
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGBA')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            max_size = THUMBNAIL_SIZES[size_variant]
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            temp_path = safe_media_path(f"{cached_path}.tmp.{os.getpid()}")
            if not temp_path:
                return original_path, fallback_content_type
            quality = 80 if size_variant == 'thumb' else 85
            img.save(temp_path, format='WEBP', quality=quality, method=4)
            os.replace(temp_path, cached_path)

        return cached_path, 'image/webp'
    except Exception as e:
        logger.warning("Failed to generate %s thumbnail for %s: %s", size_variant, original_path, e)
        return original_path, fallback_content_type


def delete_cached_thumbnails(original_path):
    """Clean up cached thumbnails when a jewellery photo is deleted or replaced."""
    original_path = safe_media_path(original_path)
    if not original_path:
        return
    cache_dir = os.path.join(os.path.dirname(original_path), 'cache')
    base_name = os.path.splitext(os.path.basename(original_path))[0]
    base_name = "".join(c for c in base_name if c.isalnum() or c in ('-', '_'))
    if not base_name:
        return
    for variant in ('thumb', 'full'):
        cached_path = safe_media_path(os.path.join(cache_dir, f"{base_name}_{variant}.webp"))
        if not cached_path:
            continue
        try:
            if os.path.exists(cached_path):
                os.remove(cached_path)
        except OSError:
            pass
