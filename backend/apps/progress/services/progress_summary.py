from datetime import date

from django.db.models import F, OuterRef, Subquery

from apps.projects.models import Project, ProjectStage

from ..models import StageProgressEntry


def get_project_progress_summary(project: Project, *, as_of_date: date) -> dict:
    """Read direct, latest eligible progress; caller must authorize the Project first."""
    latest = StageProgressEntry.objects.filter(
        stage_id=OuterRef("pk"), progress_date__lte=as_of_date
    ).order_by("-progress_date", "-id")
    stages = (
        ProjectStage.objects.filter(project=project)
        .annotate(
            stage_id=F("pk"),
            progress_entry_id=Subquery(latest.values("id")[:1]),
            progress_date=Subquery(latest.values("progress_date")[:1]),
            progress_percentage=Subquery(latest.values("progress_percentage")[:1]),
        )
        .order_by("position", "id")
        .values("stage_id", "progress_entry_id", "progress_date", "progress_percentage")
    )
    # All three subqueries select the same entry. Missing progress stays None,
    # distinct from an explicitly reported Decimal("0.00"). Materialize in one query.
    return {
        "project_id": project.pk,
        "as_of_date": as_of_date,
        "stages": list(stages),
    }
