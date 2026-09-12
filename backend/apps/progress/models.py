from decimal import Decimal

from django.db import models

STAGE_PROGRESS_DATE_CONSTRAINT = "progress_stage_date_unique"


class StageProgressEntry(models.Model):
    stage = models.ForeignKey(
        "projects.ProjectStage",
        on_delete=models.PROTECT,
        related_name="progress_entries",
    )
    progress_date = models.DateField()
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    progress_percentage__gte=Decimal("0.00"),
                    progress_percentage__lte=Decimal("100.00"),
                ),
                name="progress_percentage_range",
                violation_error_message="O percentual deve estar entre 0 e 100.",
            ),
            models.UniqueConstraint(
                fields=["stage", "progress_date"], name=STAGE_PROGRESS_DATE_CONSTRAINT
            ),
        ]
