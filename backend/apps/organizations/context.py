"""Shared validation for the organization selected in a Django session."""

from .models import Membership

CURRENT_ORGANIZATION_SESSION_KEY = "current_organization_id"
MAX_ORGANIZATION_ID = 2**63 - 1


def get_active_membership(user, organization_id):
    # Reject malformed/stale session values before querying a BigAutoField.
    if (
        type(organization_id) is not int
        or not 0 < organization_id <= MAX_ORGANIZATION_ID
    ):
        return None
    return (
        Membership.objects.select_related("organization")
        .filter(user=user, organization_id=organization_id, is_active=True)
        .first()
    )
