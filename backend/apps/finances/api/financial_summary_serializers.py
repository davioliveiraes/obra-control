from rest_framework import serializers

from ..services.financial_summary import FINANCIAL_SUMMARY_DECIMAL_PRECISION


class ProjectFinancialSummarySerializer(serializers.Serializer):
    project_id = serializers.IntegerField(read_only=True)
    revenue_total = serializers.DecimalField(
        max_digits=FINANCIAL_SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    expense_total = serializers.DecimalField(
        max_digits=FINANCIAL_SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
    realized_balance = serializers.DecimalField(
        max_digits=FINANCIAL_SUMMARY_DECIMAL_PRECISION,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
    )
