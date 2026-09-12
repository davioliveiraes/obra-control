from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.conf import settings
from django.utils import timezone
from django.utils.timezone import localdate as django_localdate
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.daily_reports.models import DailyReport, DailyReportActivity
from apps.finances.models import Expense, Revenue
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.progress.api import progress_summary_views
from apps.progress.models import StageProgressEntry
from apps.progress.services.progress_summary import get_project_progress_summary
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.progress import StageProgressEntryFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

from .test_api import detail

pytestmark = pytest.mark.django_db
AS_OF = date(2026, 9, 12)


def url(project):
    return f"/api/v1/projects/{project.pk}/progress-summary/"


@pytest.fixture(autouse=True)
def local_date(monkeypatch):
    clock = Mock(return_value=AS_OF)
    monkeypatch.setattr(progress_summary_views.timezone, "localdate", clock)
    return clock


@pytest.mark.parametrize("role", MembershipRole.values)
def test_roles_can_read_without_csrf_with_exact_decimal_and_null_contract(
    tenant_client, project, membership, role, local_date
):
    membership.role = role
    membership.save(update_fields=["role"])
    expected = []
    for percentage in ["0.00", "100.00", "33.33", "62.50", None]:
        stage = ProjectStageFactory(project=project)
        entry = (
            StageProgressEntryFactory(
                stage=stage,
                progress_percentage=Decimal(percentage),
                progress_date=AS_OF,
            )
            if percentage is not None
            else None
        )
        expected.append(
            {
                "stage_id": stage.pk,
                "progress_entry_id": entry.pk if entry is not None else None,
                "progress_date": AS_OF.isoformat() if entry is not None else None,
                "progress_percentage": percentage,
            }
        )
    tenant_client.credentials()  # Session remains; GET needs no CSRF token header.
    session_before = dict(tenant_client.session)
    response = tenant_client.get(url(project))
    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    assert response.json() == {
        "project_id": project.pk,
        "as_of_date": AS_OF.isoformat(),
        "stages": expected,
    }
    assert all(
        row["progress_percentage"] is None
        or isinstance(row["progress_percentage"], str)
        for row in response.json()["stages"]
    )
    local_date.assert_called_once_with()
    assert dict(tenant_client.session) == session_before


def test_empty_project_returns_200_with_reference_date(tenant_client, project):
    response = tenant_client.get(url(project))
    assert response.status_code == 200
    assert response.json() == {
        "project_id": project.pk,
        "as_of_date": AS_OF.isoformat(),
        "stages": [],
    }


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_only_get_head_options_with_valid_session_and_csrf(
    tenant_client, project, membership, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    for method in ["post", "patch", "put", "delete"]:
        response = getattr(tenant_client, method)(url(project), {}, format="json")
        assert response.status_code == 405
        assert set(response["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}
    head = tenant_client.head(url(project))
    assert head.status_code == 200 and head.content == b""
    assert "no-store" in head["Cache-Control"]
    options = tenant_client.options(url(project))
    assert options.status_code == 200
    assert set(options["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}
    assert not options.json().get("actions")


@pytest.mark.parametrize("superuser", [False, True])
def test_foreign_and_missing_project_are_equivalent_404_before_service(
    tenant_client, user, superuser, monkeypatch
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    foreign = StageProgressEntryFactory()
    service = Mock(side_effect=AssertionError("Unauthorized Project reached service"))
    monkeypatch.setattr(progress_summary_views, "get_project_progress_summary", service)
    response = tenant_client.get(url(foreign.stage.project))
    missing = tenant_client.get(
        "/api/v1/projects/9223372036854775807/progress-summary/"
    )
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    assert set(response.json()) == {"detail"}
    service.assert_not_called()


@pytest.mark.parametrize("superuser", [False, True])
def test_anonymous_and_missing_organization_are_denied(
    authenticated_client, project, user, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        assert client.get(url(project)).status_code == 403


def test_revoked_membership_denies_next_request(tenant_client, project, membership):
    assert tenant_client.get(url(project)).status_code == 200
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert tenant_client.get(url(project)).status_code == 403
    assert "current_organization_id" not in tenant_client.session


def test_tenant_switch_changes_access_and_results_without_session_cache(
    tenant_client, project, user
):
    own = StageProgressEntryFactory(stage=ProjectStageFactory(project=project))
    other_membership = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    other = StageProgressEntryFactory(
        stage=ProjectStageFactory(
            project=ProjectFactory(organization=other_membership.organization)
        ),
        progress_percentage=Decimal("62.50"),
    )
    assert (
        tenant_client.get(url(project)).json()["stages"][0]["progress_entry_id"]
        == own.pk
    )
    assert tenant_client.get(url(other.stage.project)).status_code == 404
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": other_membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(url(project)).status_code == 404
    session_before = dict(tenant_client.session)
    response = tenant_client.get(url(other.stage.project))
    assert response.status_code == 200
    assert response.json()["stages"] == [
        {
            "stage_id": other.stage_id,
            "progress_entry_id": other.pk,
            "progress_date": other.progress_date.isoformat(),
            "progress_percentage": "62.50",
        }
    ]
    assert dict(tenant_client.session) == session_before


def test_complete_ordered_collection_ignores_date_pagination_and_tenant_parameters(
    tenant_client, project
):
    stages = [ProjectStageFactory(project=project, position=i % 3) for i in range(31)]
    StageProgressEntryFactory(stage=stages[0], progress_date=AS_OF + timedelta(days=1))
    same_tenant = ProjectFactory(organization=project.organization)
    StageProgressEntryFactory(stage=ProjectStageFactory(project=same_tenant))
    other = StageProgressEntryFactory()
    response = tenant_client.get(
        url(project),
        {
            "as_of_date": "2100-01-01",
            "date_to": "2100-01-01",
            "page": 2,
            "page_size": 1,
            "ordering": "-id",
            "project_id": other.stage.project_id,
            "organization_id": other.stage.project.organization_id,
        },
        HTTP_X_ORGANIZATION_ID=str(other.stage.project.organization_id),
    )
    assert response.status_code == 200
    assert response.json()["as_of_date"] == AS_OF.isoformat()
    rows = response.json()["stages"]
    assert [row["stage_id"] for row in rows] == [
        stage.pk
        for stage in sorted(stages, key=lambda stage: (stage.position, stage.pk))
    ]
    assert all(
        row["progress_entry_id"] is None
        and row["progress_date"] is None
        and row["progress_percentage"] is None
        for row in rows
    )


def test_view_uses_one_local_date_when_utc_is_already_next_day(
    tenant_client, stage, monkeypatch
):
    today = StageProgressEntryFactory(stage=stage, progress_date=AS_OF)
    StageProgressEntryFactory(
        stage=stage,
        progress_date=AS_OF + timedelta(days=1),
        progress_percentage=Decimal("100.00"),
    )
    utc_instant = datetime(2026, 9, 13, 1, 30, tzinfo=UTC)
    monkeypatch.setattr(timezone, "now", lambda: utc_instant)
    local_clock = Mock(wraps=django_localdate)
    monkeypatch.setattr(progress_summary_views.timezone, "localdate", local_clock)
    assert settings.TIME_ZONE == "America/Fortaleza" and settings.USE_TZ is True
    with timezone.override(settings.TIME_ZONE):
        response = tenant_client.get(url(stage.project))
    assert response.status_code == 200
    local_clock.assert_called_once_with()
    assert utc_instant.date() != AS_OF
    assert response.json() == {
        "project_id": stage.project_id,
        "as_of_date": AS_OF.isoformat(),
        "stages": [
            {
                "stage_id": stage.pk,
                "progress_entry_id": today.pk,
                "progress_date": AS_OF.isoformat(),
                "progress_percentage": "25.00",
            }
        ],
    }


def test_authorized_edits_and_deletes_are_reflected_in_following_queries(
    tenant_client, stage
):
    older = StageProgressEntryFactory(stage=stage, progress_date=date(2026, 9, 9))
    latest = StageProgressEntryFactory(stage=stage, progress_date=AS_OF)
    future = StageProgressEntryFactory(
        stage=stage, progress_date=AS_OF + timedelta(days=1)
    )
    assert (
        tenant_client.get(url(stage.project)).json()["stages"][0]["progress_entry_id"]
        == latest.pk
    )
    assert (
        tenant_client.patch(
            detail(older), {"progress_percentage": "70.00"}, format="json"
        ).status_code
        == 200
    )
    assert (
        tenant_client.get(url(stage.project)).json()["stages"][0]["progress_entry_id"]
        == latest.pk
    )
    assert (
        tenant_client.patch(
            detail(latest), {"progress_percentage": "68.00"}, format="json"
        ).status_code
        == 200
    )
    assert (
        tenant_client.get(url(stage.project)).json()["stages"][0]["progress_percentage"]
        == "68.00"
    )
    assert tenant_client.delete(detail(latest)).status_code == 204
    assert tenant_client.get(url(stage.project)).json()["stages"] == [
        {
            "stage_id": stage.pk,
            "progress_entry_id": older.pk,
            "progress_date": "2026-09-09",
            "progress_percentage": "70.00",
        }
    ]
    assert tenant_client.delete(detail(older)).status_code == 204
    assert tenant_client.get(url(stage.project)).json()["stages"] == [
        {
            "stage_id": stage.pk,
            "progress_entry_id": None,
            "progress_date": None,
            "progress_percentage": None,
        }
    ]
    future.refresh_from_db()  # Exclusion from summary never deletes future history.


def test_service_and_get_leave_all_domain_sources_and_other_summaries_unchanged(
    tenant_client, stage
):
    StageProgressEntryFactory(stage=stage)
    StagePlanFactory(stage=stage)
    BudgetItemFactory(stage=stage)
    ExpenseFactory(project=stage.project, stage=stage)
    RevenueFactory(project=stage.project)
    report = DailyReportFactory(project=stage.project)
    DailyReportActivityFactory(daily_report=report, stage=stage)
    models = [
        Project,
        ProjectStage,
        StageProgressEntry,
        StagePlan,
        BudgetItem,
        Expense,
        Revenue,
        DailyReport,
        DailyReportActivity,
    ]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    summary_urls = [
        f"/api/v1/projects/{stage.project_id}/{name}/"
        for name in ["cost-summary", "financial-summary"]
    ]
    summaries_before = [tenant_client.get(path).json() for path in summary_urls]
    result = get_project_progress_summary(stage.project, as_of_date=AS_OF)
    assert result["stages"][0]["progress_percentage"] == Decimal("25.00")
    assert tenant_client.get(url(stage.project)).status_code == 200
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before
    assert [tenant_client.get(path).json() for path in summary_urls] == summaries_before
