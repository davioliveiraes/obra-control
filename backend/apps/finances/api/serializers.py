from decimal import Decimal

from rest_framework import serializers

from apps.projects.models import ProjectStage

from ..models import Expense, ExpenseStatus


class ExpenseSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=ExpenseStatus.choices, default=ExpenseStatus.ACTIVE
    )
    stage_id = serializers.PrimaryKeyRelatedField(
        source="stage",
        queryset=ProjectStage.objects.none(),
        required=False,
        allow_null=True,
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Etapa indisponível."},
        help_text="Etapa opcional do Project da URL; null representa despesa geral da obra.",
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        coerce_to_string=True,
    )

    class Meta:
        model = Expense
        fields = (
            "id",
            "stage_id",
            "description",
            "amount",
            "expense_date",
            "status",
            "notes",
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
