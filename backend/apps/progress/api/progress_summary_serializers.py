from rest_framework import serializers


class StageProgressSummarySerializer(serializers.Serializer):
    stage_id = serializers.IntegerField(read_only=True)
    progress_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    progress_date = serializers.DateField(read_only=True, allow_null=True)
    progress_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
        read_only=True,
    )


class ProjectProgressSummarySerializer(serializers.Serializer):
    project_id = serializers.IntegerField(read_only=True)
    as_of_date = serializers.DateField(
        read_only=True,
        help_text="Data local utilizada pelo servidor; não é um filtro público.",
    )
    stages = StageProgressSummarySerializer(many=True, read_only=True)
