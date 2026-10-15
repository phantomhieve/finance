"""Merchant and category knowledge base service: cached lookups, database catalog, and continuous AI expansion."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import BrandKnowledge

logger = logging.getLogger(__name__)

# In-memory fast caches populated from database
_BRAND_CACHE: dict[str, tuple[str, str, str]] = {}
_BRAND_TOKENS_CACHE: list[str] = []
_KEYWORD_CACHE: list[tuple[str, str, str]] = []
_CATEGORY_CACHE: dict[str, dict[str, Any]] = {}
_CATEGORY_TEMPLATES: list[tuple[str, str, str, int]] = []
_CACHE_INITIALIZED: bool = False


def ensure_seed_knowledge() -> None:
    """Ensure database has seed records if tables are empty (e.g. during isolated tests)."""
    from .models import BrandKnowledge, CategoryTemplate, KeywordKnowledge

    try:
        need_cats = not CategoryTemplate.objects.exists()
        need_brands = not BrandKnowledge.objects.filter(merchant_key='SWIGGY').exists()
        need_kws = not KeywordKnowledge.objects.exists()

        if need_cats or need_brands or need_kws:
            import importlib

            seed_mod = importlib.import_module('expenses.migrations.0006_seed_defaults')
            default_brands = getattr(seed_mod, 'DEFAULT_BRANDS', [])
            default_cats = getattr(seed_mod, 'DEFAULT_CATEGORIES', [])
            default_kws = getattr(seed_mod, 'DEFAULT_KEYWORDS', [])

            if need_cats:
                CategoryTemplate.objects.bulk_create([
                    CategoryTemplate(name=n, kind=k, icon=i, hue=h, sort_order=s)
                    for n, k, i, h, s in default_cats
                ], ignore_conflicts=True)

            if need_brands:
                BrandKnowledge.objects.bulk_create([
                    BrandKnowledge(
                        merchant_key=k,
                        display_name=d,
                        category_name=c,
                        icon=i,
                        source='SEED',
                        confidence=1.0,
                    )
                    for k, d, c, i in default_brands
                ], ignore_conflicts=True)

            if need_kws:
                KeywordKnowledge.objects.bulk_create([
                    KeywordKnowledge(keyword=kw, category_name=cat, icon=ic, sort_order=so)
                    for kw, cat, ic, so in default_kws
                ], ignore_conflicts=True)

            invalidate_caches()
    except Exception as exc:
        logger.debug("ensure_seed_knowledge skipped: %s", exc)


def load_knowledge_cache(force: bool = False) -> None:
    """Load all brand knowledge, keywords, and category templates into memory for zero-latency lookups."""
    global _BRAND_CACHE, _BRAND_TOKENS_CACHE, _KEYWORD_CACHE
    global _CATEGORY_CACHE, _CATEGORY_TEMPLATES, _CACHE_INITIALIZED

    if _CACHE_INITIALIZED and not force:
        return

    from .models import BrandKnowledge, CategoryTemplate, KeywordKnowledge

    ensure_seed_knowledge()

    try:
        # 1. Load CategoryTemplate
        cat_templates: list[tuple[str, str, str, int]] = []
        cat_map: dict[str, dict[str, Any]] = {}
        for c in CategoryTemplate.objects.all().order_by('sort_order', 'id'):
            cat_templates.append((c.name, c.kind, c.icon, c.hue))
            cat_map[c.name] = {
                'kind': c.kind,
                'icon': c.icon,
                'hue': c.hue,
                'sort_order': c.sort_order,
            }
        _CATEGORY_TEMPLATES = cat_templates
        _CATEGORY_CACHE = cat_map

        # 2. Load BrandKnowledge
        brand_cache: dict[str, tuple[str, str, str]] = {}
        for r in BrandKnowledge.objects.all():
            brand_cache[r.merchant_key] = (r.display_name, r.category_name, r.icon)
        _BRAND_CACHE = brand_cache
        _BRAND_TOKENS_CACHE = sorted(brand_cache.keys(), key=len, reverse=True)

        # 3. Load KeywordKnowledge
        keyword_rules: list[tuple[str, str, str]] = []
        for kw in KeywordKnowledge.objects.all().order_by('sort_order', 'id'):
            keyword_rules.append((kw.keyword, kw.category_name, kw.icon))
        _KEYWORD_CACHE = keyword_rules

        _CACHE_INITIALIZED = True
    except Exception as exc:
        logger.debug("Failed to load knowledge tables from DB (migrations may be pending): %s", exc)


def invalidate_caches() -> None:
    """Clear memory caches so next lookup refreshes from the database."""
    global _CACHE_INITIALIZED
    _CACHE_INITIALIZED = False


def get_category_templates() -> list[tuple[str, str, str, int]]:
    """Return system-level default category specifications from CategoryTemplate table."""
    load_knowledge_cache()
    return list(_CATEGORY_TEMPLATES)


def get_category_icon(category_name: str) -> str:
    """Return default Material Symbols icon for a category from CategoryTemplate table."""
    load_knowledge_cache()
    info = _CATEGORY_CACHE.get(category_name)
    if info and info.get('icon'):
        return info['icon']
    return 'category'


def get_category_hue(category_name: str) -> int:
    """Return default color hue (0-360) for a category from CategoryTemplate table."""
    load_knowledge_cache()
    info = _CATEGORY_CACHE.get(category_name)
    if info and 'hue' in info:
        return info['hue']
    return 230


def lookup_brand(merchant_key: str) -> tuple[str, str, str] | None:
    """Find brand info (display_name, category_name, icon) for a given normalized merchant key."""
    if not merchant_key:
        return None
    load_knowledge_cache()
    return _BRAND_CACHE.get(merchant_key)


def get_brand_tokens() -> list[str]:
    """Return all known brand tokens sorted longest-first for substring matching."""
    load_knowledge_cache()
    return _BRAND_TOKENS_CACHE


def get_keyword_rules() -> list[tuple[str, str, str]]:
    """Return all keyword rules ordered by sort_order: (keyword, category_name, icon)."""
    load_knowledge_cache()
    return _KEYWORD_CACHE


def record_ai_brand(
    merchant_key: str,
    display_name: str,
    category_name: str,
    icon: str | None = None,
    confidence: float = 1.0,
) -> BrandKnowledge | None:
    """Expand the database knowledge base when AI categorizes a new merchant with high confidence."""
    if not merchant_key or not category_name:
        return None

    clean_key = re.sub(r'[^A-Z0-9]', '', merchant_key.upper())[:60]
    if not clean_key or len(clean_key) < 3:
        return None

    from .models import BrandKnowledge

    target_icon = icon or get_category_icon(category_name)
    clean_display = (display_name or clean_key).strip()
    if clean_display.isupper() or clean_display.islower():
        clean_display = clean_display.title()

    try:
        obj, created = BrandKnowledge.objects.get_or_create(
            merchant_key=clean_key,
            defaults={
                'display_name': clean_display[:120],
                'category_name': category_name[:60],
                'icon': target_icon[:40],
                'source': 'AI',
                'confidence': max(0.0, min(1.0, float(confidence))),
                'hits': 1,
            },
        )
        if not created:
            BrandKnowledge.objects.filter(pk=obj.pk).update(hits=obj.hits + 1)

        # Update in-memory caches dynamically
        _BRAND_CACHE[clean_key] = (obj.display_name, obj.category_name, obj.icon)
        if clean_key not in _BRAND_TOKENS_CACHE:
            _BRAND_TOKENS_CACHE.append(clean_key)
            _BRAND_TOKENS_CACHE.sort(key=len, reverse=True)

        return obj
    except Exception as exc:
        logger.warning("Could not record AI-discovered brand knowledge for %s: %s", clean_key, exc)
        return None


class _CategoryDefaultIconsProxy(dict):
    """Dynamic dictionary proxy that retrieves icons directly from CategoryTemplate in database."""

    def __getitem__(self, key: str) -> str:
        return get_category_icon(key)

    def get(self, key: str, default: str = 'category') -> str:  # type: ignore[override]
        icon = get_category_icon(key)
        return icon if icon != 'category' else default

    def __contains__(self, key: object) -> bool:
        load_knowledge_cache()
        return key in _CATEGORY_CACHE


# Dynamic dictionary proxy so legacy code referencing CATEGORY_DEFAULT_ICONS pulls directly from DB
CATEGORY_DEFAULT_ICONS = _CategoryDefaultIconsProxy()
