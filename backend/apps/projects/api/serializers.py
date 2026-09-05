from rest_framework import serializers

from apps.customers.models import Customer

from ..models import Project, ProjectStatus


class ProjectSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(
        choices=ProjectStatus.choices, default=ProjectStatus.PLANNING
    )
    customer_id = serializers.PrimaryKeyRelatedField(
        source="customer",
        queryset=Customer.objects.none(),
        required=False,
        allow_null=True,
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Cliente indisponível."},
        help_text="Cliente opcional da organização ativa; null remove o vínculo.",
    )

    class Meta:
        model = Project
        fields = (
            "id",
            "name",
            "customer_id",
            "status",
            "description",
            "planned_start_date",
            "planned_end_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        organization = getattr(request, "organization", None)
        if organization is not None:
            self.fields["customer_id"].queryset = Customer.objects.filter(
                organization=organization
            )

    def validate(self, attrs):
        # PATCH must compare supplied values with the other date already persisted.
        start = attrs.get(
            "planned_start_date", getattr(self.instance, "planned_start_date", None)
        )
        end = attrs.get(
            "planned_end_date", getattr(self.instance, "planned_end_date", None)
        )
        if start is not None and end is not None and end < start:
            raise serializers.ValidationError(
                {"planned_end_date": "A data final não pode ser anterior à inicial."}
            )
        return attrs
