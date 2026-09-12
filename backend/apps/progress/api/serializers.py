from decimal import Decimal

from rest_framework import serializers

from ..models import StageProgressEntry

DUPLICATE_PROGRESS_MESSAGE = (
    "Já existe um registro de progresso para esta etapa nesta data."
)


class StageProgressEntrySerializer(serializers.ModelSerializer):
    progress_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        coerce_to_string=True,
    )

    class Meta:
        model = StageProgressEntry
        fields = (
            "id",
            "progress_date",
            "progress_percentage",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        # Stage is supplied by the validated URL; uniqueness is scoped below.
        validators = []

    def validate_progress_date(self, value):
        queryset = StageProgressEntry.objects.filter(
            stage=self.context["stage"], progress_date=value
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(DUPLICATE_PROGRESS_MESSAGE)
        return value
