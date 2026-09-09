from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.daily_reports.models import DailyReport, DailyReportActivity
from apps.organizations.models import MembershipRole
from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db


def listing(project):
    return f"/api/v1/projects/{project.pk}/daily-reports/"


def detail(report):
    return f"{listing(report.project)}{report.pk}/"


def activities(report):
    return f"{detail(report)}activities/"


def activity_detail(activity):
    return f"{activities(activity.daily_report)}{activity.pk}/"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_report_crud_url_context_and_no_nested_writes(
    tenant_client, project, membership, role
):
    membership.role = role
    membership.save()
    foreign = ProjectFactory()
    response = tenant_client.post(
        listing(project),
        {
            "report_date": "2020-01-01",
            "weather_notes": "Chuva pela manhã",
            "general_notes": "Registro retroativo",
            "project": foreign.pk,
            "project_id": foreign.pk,
            "organization": foreign.organization_id,
            "organization_id": foreign.organization_id,
            "activities": [{"description": "Não criar"}],
        },
        format="json",
    )
    assert response.status_code == 201
    report = DailyReport.objects.get()
    assert report.project == project and report.report_date == date(2020, 1, 1)
    assert not report.activities.exists()
    assert set(response.json()) == {
        "id",
        "report_date",
        "weather_notes",
        "general_notes",
        "created_at",
        "updated_at",
    }
    assert tenant_client.get(detail(report)).json() == response.json()
    assert tenant_client.get(listing(project)).json()["results"] == [response.json()]
    response = tenant_client.patch(
        detail(report),
        {
            "report_date": "2020-01-02",
            "weather_notes": "",
            "general_notes": "Atualizado",
            "project_id": foreign.pk,
            "project": foreign.pk,
        },
        format="json",
    )
    assert response.status_code == 200
    report.refresh_from_db()
    assert report.report_date == date(2020, 1, 2) and report.project == project
    assert report.weather_notes == "" and report.general_notes == "Atualizado"
    activity = DailyReportActivityFactory(daily_report=report)
    assert tenant_client.delete(detail(report)).status_code == 204
    assert not DailyReport.objects.filter(pk=report.pk).exists()
    assert not DailyReportActivity.objects.filter(pk=activity.pk).exists()
    project.refresh_from_db()


def test_report_duplicate_create_and_patch_preserve_state(tenant_client, report):
    second = DailyReportFactory(project=report.project, report_date=date(2026, 9, 9))
    before = list(DailyReport.objects.order_by("pk").values())
    for method, url in [("post", listing(report.project)), ("patch", detail(second))]:
        response = getattr(tenant_client, method)(
            url,
            {
                "report_date": report.report_date.isoformat(),
                "general_notes": "Não salvar",
            },
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {
            "report_date": ["Já existe um RDO para esta obra nesta data."]
        }
        assert list(DailyReport.objects.order_by("pk").values()) == before
    assert (
        tenant_client.patch(
            detail(report),
            {"report_date": report.report_date.isoformat()},
            format="json",
        ).status_code
        == 200
    )
    assert (
        tenant_client.patch(
            detail(report), {"general_notes": "Sem alterar data"}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "report_date"),
        ({"report_date": None}, "report_date"),
        ({"report_date": "2026-02-30"}, "report_date"),
        ({"report_date": "2026-09-08", "weather_notes": "x" * 256}, "weather_notes"),
    ],
)
def test_report_invalid_payload(tenant_client, project, payload, field):
    response = tenant_client.post(listing(project), payload, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not DailyReport.objects.exists()


def test_report_fixed_pagination_order_and_defaults(tenant_client, project):
    reports = [
        DailyReportFactory(
            project=project, report_date=date(2026, 1, 1) + timedelta(days=i)
        )
        for i in range(27)
    ]
    DailyReportFactory()
    expected = [report.pk for report in reversed(reports)]
    first = tenant_client.get(
        listing(project), {"page_size": 10000, "ordering": "report_date"}
    ).json()
    second = tenant_client.get(listing(project), {"page": 2}).json()
    assert first["count"] == 27 and len(first["results"]) == 25
    assert [item["id"] for item in first["results"] + second["results"]] == expected
    response = tenant_client.post(
        listing(project), {"report_date": "2025-01-01"}, format="json"
    )
    assert response.status_code == 201
    assert response.json()["weather_notes"] == response.json()["general_notes"] == ""


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_activity_crud_optional_stage_and_immutable_report(
    tenant_client, report, stage, membership, role
):
    membership.role = role
    membership.save()
    other = DailyReportFactory()
    response = tenant_client.post(
        activities(report),
        {
            "description": "Organização do canteiro",
            "daily_report": other.pk,
            "daily_report_id": other.pk,
            "project_id": other.project_id,
            "organization_id": other.project.organization_id,
        },
        format="json",
    )
    assert response.status_code == 201
    activity = DailyReportActivity.objects.get()
    assert (
        activity.daily_report == report
        and activity.stage is None
        and activity.position == 0
    )
    assert set(response.json()) == {
        "id",
        "stage_id",
        "description",
        "position",
        "created_at",
        "updated_at",
    }
    assert tenant_client.get(activity_detail(activity)).json() == response.json()
    for new_stage in [stage, ProjectStageFactory(project=report.project), None]:
        response = tenant_client.patch(
            activity_detail(activity),
            {
                "stage_id": new_stage.pk if new_stage else None,
                "position": 2,
                "description": "Concretagem",
                "daily_report_id": other.pk,
            },
            format="json",
        )
        assert response.status_code == 200
        activity.refresh_from_db()
        assert activity.stage == new_stage and activity.daily_report == report
        assert activity.position == 2 and activity.description == "Concretagem"
    created = tenant_client.post(
        activities(report),
        {"stage_id": stage.pk, "description": "Etapa"},
        format="json",
    )
    assert created.status_code == 201 and created.json()["stage_id"] == stage.pk
    created_null = tenant_client.post(
        activities(report), {"stage_id": None, "description": "Geral"}, format="json"
    )
    assert created_null.status_code == 201 and created_null.json()["stage_id"] is None
    assert tenant_client.delete(activity_detail(activity)).status_code == 204
    assert not DailyReportActivity.objects.filter(pk=activity.pk).exists()
    report.refresh_from_db()
    stage.refresh_from_db()


def test_activities_flat_unpaginated_and_ordered(tenant_client, report):
    items = [
        DailyReportActivityFactory(daily_report=report, position=i % 3)
        for i in range(28)
    ]
    DailyReportActivityFactory()
    response = tenant_client.get(activities(report), {"page": 2, "ordering": "-id"})
    assert response.status_code == 200 and isinstance(response.json(), list)
    assert [row["id"] for row in response.json()] == [
        item.pk for item in sorted(items, key=lambda item: (item.position, item.pk))
    ]


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "description"),
        ({"description": ""}, "description"),
        ({"description": "   "}, "description"),
        ({"description": None}, "description"),
        ({"description": "Obra", "position": -1}, "position"),
        ({"description": "Obra", "position": 2**31}, "position"),
        ({"description": "Obra", "stage_id": "invalid"}, "stage_id"),
    ],
)
def test_activity_invalid_payload(tenant_client, report, payload, field):
    response = tenant_client.post(activities(report), payload, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not DailyReportActivity.objects.exists()


@pytest.mark.parametrize("source", ["missing", "other_project", "other_tenant"])
def test_activity_stage_resolution_rejects_external_ids_on_create_and_patch(
    tenant_client, activity, source
):
    if source == "missing":
        stage_id = 2**63 - 1
    else:
        project = (
            ProjectFactory(organization=activity.daily_report.project.organization)
            if source == "other_project"
            else ProjectFactory()
        )
        stage_id = ProjectStageFactory(project=project).pk
    before = DailyReportActivity.objects.values().get(pk=activity.pk)
    for method, url in [
        ("post", activities(activity.daily_report)),
        ("patch", activity_detail(activity)),
    ]:
        response = getattr(tenant_client, method)(
            url, {"stage_id": stage_id, "description": "Não salvar"}, format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"stage_id": ["Etapa indisponível."]}
        activity.refresh_from_db()
        assert DailyReportActivity.objects.values().get(pk=activity.pk) == before
        assert DailyReportActivity.objects.count() == 1


@pytest.mark.parametrize("external_tenant", [False, True])
def test_report_cross_project_and_cross_tenant_objects_stay_hidden(
    tenant_client, report, external_tenant
):
    other_project = (
        ProjectFactory()
        if external_tenant
        else ProjectFactory(organization=report.project.organization)
    )
    other_report = DailyReportFactory(project=other_project)
    other_activity = DailyReportActivityFactory(daily_report=other_report)
    before = DailyReport.objects.values().get(pk=other_report.pk)
    wrong_detail = f"{listing(report.project)}{other_report.pk}/"
    for method in ["get", "patch", "delete"]:
        response = getattr(tenant_client, method)(
            wrong_detail, {"general_notes": "Não salvar"}, format="json"
        )
        assert response.status_code == 404
        url = f"{wrong_detail}activities/{other_activity.pk}/"
        assert (
            getattr(tenant_client, method)(
                url, {"description": "Não salvar"}, format="json"
            ).status_code
            == 404
        )
    wrong_activities = f"{wrong_detail}activities/"
    assert tenant_client.get(wrong_activities).status_code == 404
    assert (
        tenant_client.post(
            wrong_activities, {"description": "Não salvar"}, format="json"
        ).status_code
        == 404
    )
    if external_tenant:
        assert tenant_client.get(listing(other_project)).status_code == 404
        assert (
            tenant_client.post(
                listing(other_project), {"report_date": "2026-01-01"}, format="json"
            ).status_code
            == 404
        )
        assert tenant_client.get(activities(other_report)).status_code == 404
    assert DailyReport.objects.values().get(pk=other_report.pk) == before
    other_activity.refresh_from_db()
    assert other_activity.description == "Organização geral do canteiro"


def test_activity_cross_report_same_project_is_404(tenant_client, report):
    second = DailyReportFactory(project=report.project, report_date=date(2026, 9, 9))
    activity = DailyReportActivityFactory(daily_report=second)
    before = DailyReportActivity.objects.values().get(pk=activity.pk)
    for method in ["get", "patch", "delete"]:
        response = getattr(tenant_client, method)(
            f"{activities(report)}{activity.pk}/",
            {"description": "Não salvar"},
            format="json",
        )
        assert response.status_code == 404
    activity.refresh_from_db()
    assert DailyReportActivity.objects.values().get(pk=activity.pk) == before


@pytest.mark.parametrize("kind", ["report", "activity"])
def test_member_read_only_and_no_mutation(tenant_client, activity, membership, kind):
    membership.role = MembershipRole.MEMBER
    membership.save()
    collection, url = (
        (listing(activity.daily_report.project), detail(activity.daily_report))
        if kind == "report"
        else (activities(activity.daily_report), activity_detail(activity))
    )
    models = [DailyReport, DailyReportActivity]
    before = {model: list(model.objects.values()) for model in models}
    for endpoint in [collection, url]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(endpoint).status_code == 200
    for method, endpoint in [("post", collection), ("patch", url), ("delete", url)]:
        assert (
            getattr(tenant_client, method)(
                endpoint,
                {"report_date": "2026-09-10", "description": "Não salvar"},
                format="json",
            ).status_code
            == 403
        )
    assert {model: list(model.objects.values()) for model in models} == before


@pytest.mark.parametrize("kind", ["report", "activity"])
def test_csrf_revocation_and_put_remain_enforced(
    tenant_client, activity, membership, kind
):
    collection, url = (
        (listing(activity.daily_report.project), detail(activity.daily_report))
        if kind == "report"
        else (activities(activity.daily_report), activity_detail(activity))
    )
    assert tenant_client.put(url, {}, format="json").status_code == 405
    tenant_client.credentials()
    for method, endpoint in [("post", collection), ("patch", url), ("delete", url)]:
        response = getattr(tenant_client, method)(
            endpoint,
            {"report_date": "2026-09-10", "description": "Não salvar"},
            format="json",
        )
        assert response.status_code == 403 and "CSRF" in response.json()["detail"]
    assert tenant_client.get(collection).status_code == 200
    membership.is_active = False
    membership.save()
    assert tenant_client.get(collection).status_code == 403
    assert tenant_client.get(url).status_code == 403
    activity.refresh_from_db()
    activity.daily_report.refresh_from_db()


def test_superuser_obeys_membership_tenant_and_role(
    tenant_client, activity, membership, user
):
    user.is_superuser = True
    user.save()
    membership.role = MembershipRole.MEMBER
    membership.save()
    foreign = DailyReportActivityFactory()
    for collection, url, foreign_url in [
        (
            listing(activity.daily_report.project),
            detail(activity.daily_report),
            detail(foreign.daily_report),
        ),
        (
            activities(activity.daily_report),
            activity_detail(activity),
            activity_detail(foreign),
        ),
    ]:
        assert tenant_client.get(collection).status_code == 200
        assert tenant_client.get(foreign_url).status_code == 404
        assert tenant_client.patch(url, {}, format="json").status_code == 403
    membership.delete()
    assert tenant_client.get(detail(activity.daily_report)).status_code == 403
    assert tenant_client.get(activity_detail(activity)).status_code == 403


def test_anonymous_and_missing_context_denied(
    api_client, authenticated_client, activity
):
    anonymous_client = APIClient(enforce_csrf_checks=True)
    for url in [
        listing(activity.daily_report.project),
        detail(activity.daily_report),
        activities(activity.daily_report),
        activity_detail(activity),
    ]:
        assert anonymous_client.get(url).status_code == 403
        assert authenticated_client.get(url).status_code == 403
