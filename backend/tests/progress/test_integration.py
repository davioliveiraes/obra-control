import pytest
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError

from apps.budgets.models import BudgetItem
from apps.daily_reports.models import DailyReport, DailyReportActivity
from apps.finances.models import Expense, Revenue
from apps.planning.models import StagePlan
from apps.progress.api.serializers import StageProgressEntrySerializer
from apps.progress.models import StageProgressEntry
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.progress import StageProgressEntryFactory
from tests.factories.projects import ProjectStageFactory

from .test_api import detail, listing, payload

pytestmark = pytest.mark.django_db


def test_stage_with_progress_protected_and_children_restriction_preserved(
    tenant_client, stage
):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    entry = StageProgressEntryFactory(stage=child)
    plan = StagePlanFactory(stage=child)
    budget = BudgetItemFactory(stage=child)
    report = DailyReportFactory(project=stage.project)
    activity = DailyReportActivityFactory(daily_report=report, stage=child)
    expense = ExpenseFactory(project=stage.project, stage=child)
    prefix = f"/api/v1/projects/{stage.project_id}/stages/"
    parent_response = tenant_client.delete(f"{prefix}{stage.pk}/")
    assert parent_response.status_code == 409
    assert parent_response.json() == {
        "detail": "A etapa possui subetapas e não pode ser excluída."
    }
    models = [
        ProjectStage,
        StageProgressEntry,
        StagePlan,
        BudgetItem,
        DailyReportActivity,
        Expense,
    ]
    before = {model: list(model.objects.values()) for model in models}
    response = tenant_client.delete(f"{prefix}{child.pk}/")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A etapa possui registros vinculados e não pode ser excluída."
    }
    assert {model: list(model.objects.values()) for model in models} == before
    assert tenant_client.delete(detail(entry)).status_code == 204
    assert tenant_client.delete(f"{prefix}{child.pk}/").status_code == 204
    assert not StagePlan.objects.filter(pk=plan.pk).exists()
    assert not BudgetItem.objects.filter(pk=budget.pk).exists()
    activity.refresh_from_db()
    expense.refresh_from_db()
    assert activity.stage is None and expense.stage is None
    assert tenant_client.delete(f"{prefix}{stage.pk}/").status_code == 204


def test_progress_alone_protects_project_without_partial_cascades(tenant_client, stage):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    entry = StageProgressEntryFactory(stage=child)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    models = [Project, ProjectStage, StageProgressEntry, BudgetItem, StagePlan]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    response = tenant_client.delete(f"/api/v1/projects/{stage.project_id}/")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A obra possui registros vinculados e não pode ser excluída."
    }
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before
    assert tenant_client.delete(detail(entry)).status_code == 204
    assert (
        tenant_client.delete(f"/api/v1/projects/{stage.project_id}/").status_code == 204
    )
    for model in models:
        assert not model.objects.exists()


def test_progress_is_independent_of_parent_rdo_planning_and_financial_domains(
    tenant_client, stage
):
    parent = ProjectStageFactory(project=stage.project)
    stage.parent = parent
    stage.save()
    project = stage.project
    BudgetItemFactory(stage=stage)
    ExpenseFactory(project=project, stage=stage)
    RevenueFactory(project=project)
    rdo_url = f"/api/v1/projects/{project.pk}/daily-reports/"
    report_response = tenant_client.post(
        rdo_url, {"report_date": "2026-09-09"}, format="json"
    )
    assert report_response.status_code == 201
    report = DailyReport.objects.get(pk=report_response.json()["id"])
    assert (
        tenant_client.post(
            f"{rdo_url}{report.pk}/activities/",
            {"stage_id": stage.pk, "description": "Concretagem"},
            format="json",
        ).status_code
        == 201
    )
    planning_url = f"/api/v1/projects/{project.pk}/planning/"
    assert (
        tenant_client.post(
            planning_url,
            {
                "stage_id": stage.pk,
                "planned_start_date": "2000-01-01",
                "planned_end_date": "2000-01-02",
            },
            format="json",
        ).status_code
        == 201
    )
    assert not StageProgressEntry.objects.exists()
    models = [
        Project,
        ProjectStage,
        DailyReport,
        DailyReportActivity,
        StagePlan,
        BudgetItem,
        Expense,
        Revenue,
    ]
    before = {model: list(model.objects.values()) for model in models}
    urls = [
        f"/api/v1/projects/{project.pk}/{summary}/"
        for summary in ["cost-summary", "financial-summary"]
    ]
    summaries = [tenant_client.get(url).json() for url in urls]
    assert (
        tenant_client.post(listing(stage), payload(), format="json").status_code == 201
    )
    entry = StageProgressEntry.objects.get()
    assert (
        tenant_client.patch(
            detail(entry), {"progress_percentage": "33.33"}, format="json"
        ).status_code
        == 200
    )
    assert not parent.progress_entries.exists()
    assert {model: list(model.objects.values()) for model in models} == before
    assert [tenant_client.get(url).json() for url in urls] == summaries
    entry_before = StageProgressEntry.objects.values().get(pk=entry.pk)
    assert (
        tenant_client.patch(
            f"{rdo_url}{report.pk}/", {"general_notes": "Revisado"}, format="json"
        ).status_code
        == 200
    )
    plan = StagePlan.objects.get(stage=stage)
    assert (
        tenant_client.patch(
            f"{planning_url}{plan.pk}/",
            {"planned_end_date": "2000-01-03"},
            format="json",
        ).status_code
        == 200
    )
    assert StageProgressEntry.objects.values().get(pk=entry.pk) == entry_before
    assert tenant_client.delete(detail(entry)).status_code == 204
    assert all(model.objects.exists() for model in models)


def test_unexpected_protection_is_not_masked(tenant_client, stage, monkeypatch):
    def unexpected_protection(instance, *args, **kwargs):
        raise ProtectedError("Unrelated protection", {instance})

    monkeypatch.setattr(ProjectStage, "delete", unexpected_protection)
    with pytest.raises(ProtectedError, match="Unrelated protection"):
        tenant_client.delete(f"/api/v1/projects/{stage.project_id}/stages/{stage.pk}/")


def test_unrelated_integrity_error_is_not_reported_as_duplicate(
    tenant_client, stage, monkeypatch
):
    def unexpected_failure(serializer, **kwargs):
        raise IntegrityError("Unrelated integrity failure")

    monkeypatch.setattr(StageProgressEntrySerializer, "save", unexpected_failure)
    with pytest.raises(IntegrityError, match="Unrelated integrity failure"):
        tenant_client.post(listing(stage), payload(), format="json")
    assert not StageProgressEntry.objects.exists()
