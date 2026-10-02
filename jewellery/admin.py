from django.contrib import admin
from .models import JewelleryItem


@admin.register(JewelleryItem)
class JewelleryItemAdmin(admin.ModelAdmin):
    list_display = ('display_label', 'group', 'metal_type', 'purity', 'weight_grams',
                    'location', 'estimated_value', 'created_at')

    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        JewelleryItem.attach_rates(cl.result_list)
        return cl
