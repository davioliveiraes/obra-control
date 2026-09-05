from rest_framework import serializers

from ..context import MAX_ORGANIZATION_ID
from ..models import MembershipRole


class AccessibleOrganizationSerializer(serializers.Serializer):
    """Represent an organization through the requesting user's membership."""

    id = serializers.IntegerField(source="organization_id", read_only=True)
    name = serializers.CharField(source="organization.name", read_only=True)
    role = serializers.ChoiceField(choices=MembershipRole.choices, read_only=True)


class SelectOrganizationSerializer(serializers.Serializer):
    organization_id = serializers.IntegerField(
        min_value=1, max_value=MAX_ORGANIZATION_ID
    )
