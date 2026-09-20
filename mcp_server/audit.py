"""
Audit helpers for MCP write operations.

Every create / update / delete goes through these helpers so that a full
before/after snapshot is persisted in MCPAuditLog.
"""

import datetime
import json
import logging
from decimal import Decimal

from django.apps import apps
from django.utils import timezone

from .models import MCPAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _json_default(obj):
    """Handle types that the default JSON encoder can't deal with."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def serialize_instance(instance):
    """Convert a Django model instance into a JSON-safe dict of all field values."""
    data = {}
    for field in instance._meta.concrete_fields:
        value = getattr(instance, field.attname)
        # Force through JSON round-trip to ensure everything is serialisable
        try:
            json.dumps(value, default=_json_default)
            data[field.attname] = value
        except (TypeError, ValueError):
            data[field.attname] = str(value)
    # Re-serialise the whole thing so Decimals/dates are stored as strings
    return json.loads(json.dumps(data, default=_json_default))


def _model_label(instance):
    """Return 'app_label.ModelName' for an instance."""
    return f"{instance._meta.app_label}.{instance._meta.object_name}"


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log_create(instance, tool_name):
    """Record a CREATE action after the instance has been saved."""
    return MCPAuditLog.objects.create(
        action='CREATE',
        model_name=_model_label(instance),
        object_id=instance.pk,
        object_repr=str(instance)[:300],
        data_before=None,
        data_after=serialize_instance(instance),
        tool_name=tool_name,
    )


def log_update(instance, old_data, tool_name):
    """Record an UPDATE action.  `old_data` should be the result of
    serialize_instance() captured *before* saving."""
    return MCPAuditLog.objects.create(
        action='UPDATE',
        model_name=_model_label(instance),
        object_id=instance.pk,
        object_repr=str(instance)[:300],
        data_before=old_data,
        data_after=serialize_instance(instance),
        tool_name=tool_name,
    )


def log_delete(instance, tool_name):
    """Record a DELETE action *before* the instance is deleted."""
    return MCPAuditLog.objects.create(
        action='DELETE',
        model_name=_model_label(instance),
        object_id=instance.pk,
        object_repr=str(instance)[:300],
        data_before=serialize_instance(instance),
        data_after=None,
        tool_name=tool_name,
    )


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------

def revert_entry(entry: MCPAuditLog) -> str:
    """
    Undo the change described by an MCPAuditLog entry.

    - CREATE → delete the created object
    - UPDATE → restore old field values
    - DELETE → re-create the object with old field values

    Returns a human-readable summary of what was done.
    """
    if entry.reverted:
        return f"Entry #{entry.pk} has already been reverted."

    try:
        Model = apps.get_model(entry.model_name)
    except (LookupError, ValueError) as exc:
        return f"Cannot resolve model '{entry.model_name}': {exc}"

    if entry.action == 'CREATE':
        try:
            obj = Model.objects.get(pk=entry.object_id)
            obj.delete()
            msg = f"Deleted {entry.model_name}#{entry.object_id} (reverted CREATE)."
        except Model.DoesNotExist:
            msg = (
                f"{entry.model_name}#{entry.object_id} already deleted; "
                f"marking as reverted."
            )

    elif entry.action == 'UPDATE':
        if not entry.data_before:
            return f"No data_before snapshot for entry #{entry.pk}; cannot revert."
        try:
            obj = Model.objects.get(pk=entry.object_id)
        except Model.DoesNotExist:
            return f"{entry.model_name}#{entry.object_id} no longer exists."
        _apply_snapshot(obj, entry.data_before)
        obj.save()
        msg = f"Restored {entry.model_name}#{entry.object_id} to pre-update state."

    elif entry.action == 'DELETE':
        if not entry.data_before:
            return f"No data_before snapshot for entry #{entry.pk}; cannot revert."
        obj = Model()
        _apply_snapshot(obj, entry.data_before)
        obj.save()
        msg = (
            f"Re-created {entry.model_name} (new pk={obj.pk}, "
            f"original pk was {entry.object_id})."
        )

    else:
        return f"Unknown action '{entry.action}' on entry #{entry.pk}."

    entry.reverted = True
    entry.reverted_at = timezone.now()
    entry.save(update_fields=['reverted', 'reverted_at'])
    logger.info("Reverted MCP audit entry #%s: %s", entry.pk, msg)
    return msg


def _apply_snapshot(instance, data: dict):
    """Set field values on a model instance from a serialised snapshot dict."""
    field_map = {f.attname: f for f in instance._meta.concrete_fields}
    for key, value in data.items():
        field = field_map.get(key)
        if not field:
            continue
        # Skip auto-fields that Django manages
        if getattr(field, 'primary_key', False):
            # For DELETE reverts we *do* want to keep the original PK if possible
            pass
        if value is not None:
            # Convert string representations back to proper Python types
            internal_type = field.get_internal_type()
            if internal_type in ('DecimalField',) and isinstance(value, str):
                value = Decimal(value)
            elif internal_type in ('DateField',) and isinstance(value, str):
                value = datetime.date.fromisoformat(value)
            elif internal_type in ('DateTimeField',) and isinstance(value, str):
                value = datetime.datetime.fromisoformat(value)
            elif internal_type in ('IntegerField', 'PositiveIntegerField',
                                   'BigAutoField', 'AutoField',
                                   'PositiveSmallIntegerField',
                                   'SmallIntegerField'):
                if isinstance(value, str) and value.isdigit():
                    value = int(value)
            elif internal_type == 'BooleanField' and isinstance(value, str):
                value = value.lower() in ('true', '1')
        setattr(instance, key, value)
