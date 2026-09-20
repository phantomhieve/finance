from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import MCPAuditLog


@admin.register(MCPAuditLog)
class MCPAuditLogAdmin(ModelAdmin):
    list_display = ('timestamp', 'action', 'model_name', 'object_id',
                    'object_repr', 'tool_name', 'reverted')
    list_filter = ('action', 'model_name', 'reverted', 'tool_name')
    search_fields = ('object_repr', 'model_name', 'tool_name')
    readonly_fields = ('timestamp', 'action', 'model_name', 'object_id',
                       'object_repr', 'data_before', 'data_after',
                       'tool_name', 'reverted', 'reverted_at')
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
