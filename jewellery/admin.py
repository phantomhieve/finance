from django.contrib import admin
from .models import JewelleryItem

@admin.register(JewelleryItem)
class JewelleryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'metal_type', 'purity', 'weight_grams', 'location', 'estimated_value', 'created_at')
    list_filter = ('metal_type', 'location', 'category', 'group')
    search_fields = ('name', 'notes')
