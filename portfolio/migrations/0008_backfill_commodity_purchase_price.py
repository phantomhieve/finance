"""
Backfill purchase_price_per_gram for existing commodity holdings.
Sets it to the current cached rate so commodities don't inflate returns.
Users can adjust to their actual purchase price later.
"""
from django.db import migrations


def backfill_purchase_prices(apps, schema_editor):
    CommodityHolding = apps.get_model('portfolio', 'CommodityHolding')
    CommodityPrice = apps.get_model('portfolio', 'CommodityPrice')

    rates = {}
    for p in CommodityPrice.objects.all():
        rates[p.commodity_type] = p.rate_per_gram

    for h in CommodityHolding.objects.filter(purchase_price_per_gram=0):
        rate = rates.get(h.commodity_type)
        if rate:
            h.purchase_price_per_gram = rate
            h.save(update_fields=['purchase_price_per_gram'])


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0007_add_commodity_purchase_price'),
    ]

    operations = [
        migrations.RunPython(backfill_purchase_prices, migrations.RunPython.noop),
    ]
