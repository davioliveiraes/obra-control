from rest_framework import serializers

from apps.projects.models import ProjectStage

from ..models import StagePlan

DUPLICATE_PLAN_MESSAGE = "A etapa já possui planejamento."


class StagePlanSerializer(serializers.ModelSerializer):
    stage_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = StagePlan
        fields = (
            "id",
            "stage_id",
            "planned_start_date",
            "planned_end_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        # PATCH compares supplied dates with the other persisted value.
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


class StagePlanCreateSerializer(StagePlanSerializer):
    stage_id = serializers.PrimaryKeyRelatedField(
        source="stage",
        queryset=ProjectStage.objects.none(),
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Etapa indisponível."},
        help_text="Etapa do Project da URL; vínculo imutável após a criação.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        project = self.context.get("project")
        if project is not None:
            self.fields["stage_id"].queryset = ProjectStage.objects.filter(
                project=project
            )

    def validate_stage_id(self, stage):
        if StagePlan.objects.filter(stage=stage).exists():
            raise serializers.ValidationError(DUPLICATE_PLAN_MESSAGE)
        return stage
