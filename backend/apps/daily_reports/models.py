from django.core.exceptions import ValidationError
from django.db import models

from apps.projects.models import ProjectStage

DAILY_REPORT_DATE_CONSTRAINT = "daily_reports_project_date_unique"


class DailyReport(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="daily_reports"
    )
    report_date = models.DateField()
    weather_notes = models.CharField(max_length=255, blank=True)
    general_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "report_date"], name=DAILY_REPORT_DATE_CONSTRAINT
            )
        ]


class DailyReportActivity(models.Model):
    daily_report = models.ForeignKey(
        DailyReport, on_delete=models.CASCADE, related_name="activities"
    )
    stage = models.ForeignKey(
        ProjectStage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_report_activities",
    )
    description = models.TextField()
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.stage_id is None or self.daily_report_id is None:
            return
        project_id = (
            DailyReport.objects.using(self._state.db)
            .filter(pk=self.daily_report_id)
            .values_list("project_id", flat=True)
            .first()
        )
        if project_id is not None and (
            ProjectStage.objects.using(self._state.db)
            .filter(pk=self.stage_id)
            .exclude(project_id=project_id)
            .exists()
        ):
            raise ValidationError(
                {"stage": "A etapa deve pertencer à mesma obra do RDO."}
            )
