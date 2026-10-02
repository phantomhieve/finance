import os
from decimal import Decimal
from collections import defaultdict
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse, HttpResponseForbidden

from pftracker.utils import safe_redirect
from portfolio.views import _require_jewellery, _user_group
from .models import JewelleryItem
from .forms import JewelleryItemForm
from portfolio.models import CommodityPrice


@login_required
@_require_jewellery
def jewellery_dashboard(request):
    group = _user_group(request)
    items = list(JewelleryItem.objects.filter(group=group))

    # Active filters
    filter_metal = request.GET.get('metal', '')
    filter_location = request.GET.get('location', '')
    filter_category = request.GET.get('category', '')
    filter_search = request.GET.get('search', '')

    all_category_counts = defaultdict(int)
    for i in items:
        all_category_counts[i.category] += 1

    # Type chips with icon + colour + count (only types that have items)
    category_meta = []
    for val, label in JewelleryItem.CATEGORY_CHOICES:
        count = all_category_counts.get(val, 0)
        if not count:
            continue
        icon, hue = JewelleryItem.CATEGORY_META.get(val, ('category', 230))
        category_meta.append({'value': val, 'label': label, 'icon': icon,
                              'hue': hue, 'count': count})

    filtered_items = items
    if filter_metal:
        filtered_items = [i for i in filtered_items if i.metal_type == filter_metal]
    if filter_location:
        filtered_items = [i for i in filtered_items if i.location == filter_location]
    if filter_category:
        filtered_items = [i for i in filtered_items if i.category == filter_category]
    if filter_search:
        q = filter_search.lower()
        filtered_items = [i for i in filtered_items if q in i.search_blob]

    prices = {p.commodity_type: p for p in CommodityPrice.objects.filter(commodity_type__in=('GOLD', 'SILVER'))}
    gold_price, silver_price = prices.get('GOLD'), prices.get('SILVER')
    JewelleryItem.attach_rates(filtered_items, {k: p.rate_per_gram for k, p in prices.items()})

    total_weight_gold = sum((i.weight_grams for i in filtered_items if i.metal_type in ['GOLD', 'DIAMOND_OTHER']), Decimal('0.00'))
    total_weight_silver = sum((i.weight_grams for i in filtered_items if i.metal_type == 'SILVER'), Decimal('0.00'))
    total_estimated_value = sum((i.estimated_value for i in filtered_items), Decimal('0.00'))

    value_by_location = []
    for val, label in JewelleryItem.LOCATION_CHOICES:
        loc_items = [i for i in filtered_items if i.location == val]
        if not loc_items:
            continue
        value = sum((i.estimated_value for i in loc_items), Decimal('0.00'))
        value_by_location.append({
            'value': val, 'label': label, 'count': len(loc_items), 'amount': value,
            'pct': round(value / total_estimated_value * 100) if total_estimated_value else 0,
        })

    context = {
        'items': filtered_items,
        'all_items_count': len(items),
        'total_weight_gold': total_weight_gold,
        'total_weight_silver': total_weight_silver,
        'total_estimated_value': total_estimated_value,
        'value_by_location': value_by_location,
        'gold_rate': gold_price.rate_per_gram if gold_price else Decimal('0.00'),
        'silver_rate': silver_price.rate_per_gram if silver_price else Decimal('0.00'),
        'rates_as_of': gold_price.fetched_at if gold_price else None,
        'form': JewelleryItemForm(),
        'filter_metal': filter_metal,
        'filter_location': filter_location,
        'filter_category': filter_category,
        'filter_search': filter_search,
        'is_filtered': bool(filter_metal or filter_location or filter_category or filter_search),
        'category_meta': category_meta,
        'metal_choices': JewelleryItem.METAL_CHOICES,
        'location_choices': JewelleryItem.LOCATION_CHOICES,
        'is_primary': getattr(request.user, 'is_primary', False),
    }
    return render(request, 'jewellery/dashboard.html', context)


@login_required
@_require_jewellery
@require_POST
def add_item(request):
    if not getattr(request.user, 'is_primary', False):
        return HttpResponseForbidden("You do not have permission to add jewellery items.")
    form = JewelleryItemForm(request.POST, request.FILES)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.group = _user_group(request)
        obj.save()
        messages.success(request, f'Added {obj.display_label} to your collection.')
    else:
        err_list = []
        for field, errors in form.errors.items():
            field_label = form.fields[field].label or field.replace('_', ' ').capitalize()
            err_list.append(f"{field_label}: {', '.join(errors)}")
        messages.error(request, 'Failed to add item: ' + '; '.join(err_list))
    return redirect('jewellery_dashboard')


@login_required
@_require_jewellery
@require_POST
def edit_item(request, pk):
    if not getattr(request.user, 'is_primary', False):
        return HttpResponseForbidden("You do not have permission to edit jewellery items.")
    obj = get_object_or_404(JewelleryItem, pk=pk, group=_user_group(request))
    form = JewelleryItemForm(request.POST, request.FILES, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, f'Updated {obj.display_label}.')
    else:
        err_list = []
        for field, errors in form.errors.items():
            field_label = form.fields[field].label or field.replace('_', ' ').capitalize()
            err_list.append(f"{field_label}: {', '.join(errors)}")
        messages.error(request, 'Failed to update item: ' + '; '.join(err_list))
    return safe_redirect(request, 'jewellery_dashboard')


@login_required
@_require_jewellery
@require_POST
def delete_item(request, pk):
    if not getattr(request.user, 'is_primary', False):
        return HttpResponseForbidden("You do not have permission to delete jewellery items.")
        
    obj = get_object_or_404(JewelleryItem, pk=pk, group=_user_group(request))
    label = obj.display_label
    obj.delete()
    messages.success(request, f'Deleted {label}.')
    return safe_redirect(request, 'jewellery_dashboard')

@login_required
@_require_jewellery
def detail_item(request, pk):
    obj = get_object_or_404(JewelleryItem, pk=pk, group=_user_group(request))
    rates = JewelleryItem.attach_rates([obj])

    context = {
        'item': obj,
        'form': JewelleryItemForm(instance=obj),
        'is_primary': getattr(request.user, 'is_primary', False),
        'gold_rate': rates.get('GOLD', Decimal('0.00')),
        'silver_rate': rates.get('SILVER', Decimal('0.00')),
    }
    return render(request, 'jewellery/detail.html', context)

@login_required
@_require_jewellery
def search_autocomplete(request):
    q = request.GET.get('q', '').strip().lower()
    if not q:
        return JsonResponse({'results': []})
        
    group = _user_group(request)
    items = JewelleryItem.objects.filter(group=group)

    results = []
    for item in items:
        if q in item.search_blob:
            results.append({
                'id': item.pk,
                'label': item.display_label,
                'category': item.get_category_display(),
                'icon': item.category_icon,
                'hue': item.category_hue,
                'location': item.get_location_display(),
                'weight': f'{item.weight_grams:g}g',
                'photo_url': (
                    f"{reverse('jewellery_photo', args=[item.pk])}?t={item.updated_at.timestamp()}" if item.photo else ''
                ),
            })
            if len(results) >= 8:  # Limit suggestions
                break

    return JsonResponse({'results': results})


# Map stored extension -> a fixed, safe image content type. We deliberately
# never derive the content type from the filename via mimetypes (which could
# yield text/html for a maliciously named file and enable stored XSS).
_SAFE_PHOTO_CONTENT_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}


@login_required
@_require_jewellery
def serve_photo(request, pk):
    """
    Secure media serving. Verifies authentication, portfolio access,
    and that the requested item belongs to the user's AccountGroup.
    The content type is forced to a known-safe image type so a file can
    never be served as HTML/script.
    """
    obj = get_object_or_404(JewelleryItem, pk=pk, group=_user_group(request))
    if not obj.photo or not obj.photo.name:
        raise Http404("Photo not found")

    ext = os.path.splitext(obj.photo.name)[1].lower()
    content_type = _SAFE_PHOTO_CONTENT_TYPES.get(ext)
    if content_type is None:
        raise Http404("Unsupported media type")

    file_path = obj.photo.path
    if not os.path.exists(file_path):
        raise Http404("File does not exist")

    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = (
        f'inline; filename="{os.path.basename(obj.photo.name)}"'
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=86400'
    return response
