from django.db import models
from django.utils import timezone


class MCPAuditLog(models.Model):
    """
    Every create / update / delete performed via the MCP server is recorded here.
    Stores full before/after snapshots as JSON so any change can be reviewed or
    reverted without touching backups.
    """

    ACTION_CHOICES = (
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    )

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(
        max_length=100,
        help_text="app_label.ModelName, e.g. 'portfolio.FixedDeposit'",
    )
    object_id = models.PositiveIntegerField()
    object_repr = models.CharField(max_length=300, blank=True)
    data_before = models.JSONField(
        null=True, blank=True,
        help_text="Full field snapshot before the change (null for CREATE)",
    )
    data_after = models.JSONField(
        null=True, blank=True,
        help_text="Full field snapshot after the change (null for DELETE)",
    )
    tool_name = models.CharField(
        max_length=100,
        help_text="MCP tool that triggered this action",
    )
    reverted = models.BooleanField(default=False)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'MCP Audit Log'
        verbose_name_plural = 'MCP Audit Logs'
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['-timestamp', 'action']),
        ]

    def __str__(self):
        status = ' [REVERTED]' if self.reverted else ''
        return (
            f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} "
            f"{self.model_name}#{self.object_id}{status}"
        )
