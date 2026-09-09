from rest_framework import serializers

from apps.projects.models import ProjectStage

from ..models import DailyReport, DailyReportActivity

DUPLICATE_REPORT_MESSAGE = "Já existe um RDO para esta obra nesta data."


class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = (
            "id",
            "report_date",
            "weather_notes",
            "general_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        # Project is supplied by the URL, not a writable serializer field.
        validators = []

    def validate_report_date(self, value):
        queryset = DailyReport.objects.filter(
            project=self.context["project"], report_date=value
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(DUPLICATE_REPORT_MESSAGE)
        return value


class DailyReportActivitySerializer(serializers.ModelSerializer):
    stage_id = serializers.PrimaryKeyRelatedField(
        source="stage",
        queryset=ProjectStage.objects.none(),
        required=False,
        allow_null=True,
        pk_field=serializers.IntegerField(min_value=1, max_value=2**63 - 1),
        error_messages={"does_not_exist": "Etapa indisponível."},
        help_text="Etapa opcional da mesma obra do RDO; null indica atividade geral.",
    )

    class Meta:
        model = DailyReportActivity
        fields = (
            "id",
            "stage_id",
            "description",
            "position",
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
