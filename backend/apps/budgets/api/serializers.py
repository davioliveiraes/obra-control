from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from apps.projects.models import ProjectStage

from ..models import BudgetItem


class BudgetItemSerializer(serializers.ModelSerializer):
    stage_id = serializers.PrimaryKeyRelatedField(
        source="stage",
        queryset=ProjectStage.objects.none(),
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Etapa indisponível."},
        help_text="Etapa do Project da URL; pode mudar somente dentro da mesma obra.",
    )
    quantity = serializers.DecimalField(
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        coerce_to_string=True,
    )
    unit_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.00"),
        coerce_to_string=True,
    )
    # Up to 22 integer digits in the product, plus two monetary decimal places.
    total = serializers.DecimalField(
        max_digits=24,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
        rounding=ROUND_HALF_UP,
        help_text="quantity × unit_price, arredondado com ROUND_HALF_UP; nunca persistido.",
    )

    class Meta:
        model = BudgetItem
        fields = (
            "id",
            "stage_id",
            "description",
            "unit",
            "quantity",
            "unit_price",
            "total",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project is not None:
            self.fields["stage_id"].queryset = ProjectStage.objects.filter(
                project=project
            )
