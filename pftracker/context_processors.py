"""
Template context processors for Vault Finance.
"""


def household_config(request):
    """Inject the HouseholdConfig for the current user's group into every template."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}
    group = getattr(request.user, 'group', None)
    if not group:
        return {}
    try:
        config = group.config
    except Exception:
        # HouseholdConfig may not exist yet (race / legacy data)
        from tracker.models import HouseholdConfig
        config, _ = HouseholdConfig.objects.get_or_create(group=group)
    return {'household_config': config}
