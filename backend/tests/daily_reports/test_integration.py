from datetime import date

import pytest

from apps.budgets.models import BudgetItem
from apps.daily_reports.models import DailyReport, DailyReportActivity
from apps.finances.models import Expense, Revenue
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

from .test_api import activities, activity_detail, detail, listing

pytestmark = pytest.mark.django_db


def test_leaf_stage_set_null_preserves_history_and_parent_restriction(
    tenant_client, report, stage
):
    leaf = ProjectStageFactory(project=report.project, parent=stage)
    activity = DailyReportActivityFactory(daily_report=report, stage=leaf)
    before = DailyReportActivity.objects.values().get(pk=activity.pk)
    prefix = f"/api/v1/projects/{report.project_id}/stages/"
    assert tenant_client.delete(f"{prefix}{stage.pk}/").status_code == 409
    assert tenant_client.delete(f"{prefix}{leaf.pk}/").status_code == 204
    activity.refresh_from_db()
    report.refresh_from_db()
    assert activity.stage is None
    assert DailyReportActivity.objects.values().get(pk=activity.pk) == {
        **before,
        "stage_id": None,
    }
    stage.refresh_from_db()


@pytest.mark.parametrize("with_financial_records", [False, True])
def test_report_protects_entire_project_graph_without_partial_deletion(
    tenant_client, report, stage, with_financial_records
):
    DailyReportActivityFactory(daily_report=report, stage=stage)
    StagePlanFactory(stage=stage)
    BudgetItemFactory(stage=stage)
    if with_financial_records:
        ExpenseFactory(project=report.project, stage=stage)
        RevenueFactory(project=report.project, status="canceled")
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
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    response = tenant_client.delete(f"/api/v1/projects/{report.project_id}/")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A obra possui registros vinculados e não pode ser excluída."
    }
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before
    assert tenant_client.delete(detail(report)).status_code == 204
    assert not DailyReportActivity.objects.exists()
    response = tenant_client.delete(f"/api/v1/projects/{report.project_id}/")
    assert response.status_code == (409 if with_financial_records else 204)


def test_rdo_writes_do_not_change_planning_budget_finances_or_summaries(
    tenant_client, project, stage
):
    BudgetItemFactory(stage=stage)
    StagePlanFactory(stage=stage)
    ExpenseFactory(project=project, stage=stage)
    RevenueFactory(project=project)
    models = [Project, ProjectStage, BudgetItem, StagePlan, Expense, Revenue]
    before = {model: list(model.objects.values()) for model in models}
    urls = [
        f"/api/v1/projects/{project.pk}/{summary}/"
        for summary in ["cost-summary", "financial-summary"]
    ]
    summaries = [tenant_client.get(url).json() for url in urls]
    response = tenant_client.post(
        listing(project), {"report_date": "2026-09-08"}, format="json"
    )
    assert response.status_code == 201
    report = DailyReport.objects.get(pk=response.json()["id"])
    response = tenant_client.post(
        activities(report),
        {"description": "Concretagem", "stage_id": stage.pk},
        format="json",
    )
    assert response.status_code == 201
    activity = DailyReportActivity.objects.get(pk=response.json()["id"])
    assert (
        tenant_client.patch(
            activity_detail(activity), {"description": "Revisada"}, format="json"
        ).status_code
        == 200
    )
    assert (
        tenant_client.patch(
            detail(report), {"weather_notes": "Chuva"}, format="json"
        ).status_code
        == 200
    )
    assert tenant_client.delete(detail(report)).status_code == 204
    assert {model: list(model.objects.values()) for model in models} == before
    assert [tenant_client.get(url).json() for url in urls] == summaries


def test_switching_organization_changes_report_visibility_and_effective_role(
    tenant_client, activity, user
):
    second = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    other = DailyReportActivityFactory(
        daily_report=DailyReportFactory(
            project=ProjectFactory(organization=second.organization),
            report_date=date(2026, 9, 9),
        )
    )
    assert tenant_client.get(activity_detail(activity)).status_code == 200
    assert tenant_client.get(activity_detail(other)).status_code == 404
    response = tenant_client.put(
        "/api/v1/organizations/current/",
        {"organization_id": second.organization_id},
        format="json",
    )
    assert response.status_code == 200
    for url in [detail(activity.daily_report), activity_detail(activity)]:
        assert tenant_client.get(url).status_code == 404
    for url in [detail(other.daily_report), activity_detail(other)]:
        assert tenant_client.get(url).status_code == 200
        assert tenant_client.patch(url, {}, format="json").status_code == 403
