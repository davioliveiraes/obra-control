from rest_framework import serializers

from ..services.cost_summary import SUMMARY_DECIMAL_PRECISION


class CostSummaryStageSerializer(serializers.Serializer):
    stage_id = serializers.IntegerField(read_only=True)
    budget_total = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    actual_total = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    variance_amount = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )


class CostSummarySerializer(serializers.Serializer):
    project_id = serializers.IntegerField(read_only=True)
    budget_total = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    actual_total = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    variance_amount = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    unallocated_actual_total = serializers.DecimalField(
        max_digits=SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    stages = CostSummaryStageSerializer(many=True, read_only=True)
