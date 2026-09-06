from django.db import models


class StagePlan(models.Model):
    stage = models.OneToOneField(
        "projects.ProjectStage", on_delete=models.CASCADE, related_name="plan"
    )
    planned_start_date = models.DateField()
    planned_end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    planned_end_date__gte=models.F("planned_start_date")
                ),
                name="planning_stageplan_planned_dates_order",
                violation_error_message="A data final não pode ser anterior à inicial.",
            ),
        ]
