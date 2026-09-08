from decimal import Decimal

from rest_framework import serializers

from ..models import Revenue, RevenueStatus


class RevenueSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=RevenueStatus.choices, default=RevenueStatus.ACTIVE
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        coerce_to_string=True,
    )

    class Meta:
        model = Revenue
        fields = (
            "id",
            "description",
            "amount",
            "revenue_date",
            "status",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
