from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
FIELDS = {
    "id",
    "stage_id",
    "planned_start_date",
    "planned_end_date",
    "created_at",
    "updated_at",
}
DATES = {"planned_start_date": "2026-10-01", "planned_end_date": "2026-10-20"}


def listing(project):
    return f"/api/v1/projects/{project.pk}/planning/"


def detail(plan):
    return f"{listing(plan.stage.project)}{plan.pk}/"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_crud_preserves_stage_and_disallows_put(tenant_client, membership, stage, role):
    membership.role = role
    membership.save(update_fields=["role"])
    assert tenant_client.get(listing(stage.project)).json() == []
    response = tenant_client.post(
        listing(stage.project), {"stage_id": stage.pk, **DATES}, format="json"
    )
    assert response.status_code == 201
    assert set(response.json()) == FIELDS
    plan = StagePlan.objects.get(pk=response.json()["id"])
    assert plan.stage == stage
    assert response.json()["stage_id"] == stage.pk
    assert tenant_client.get(detail(plan)).json() == response.json()
    response = tenant_client.patch(
        detail(plan), {"planned_end_date": "2026-10-01"}, format="json"
    )
    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.planned_start_date == plan.planned_end_date == date(2026, 10, 1)
    assert plan.updated_at > plan.created_at
    response = tenant_client.patch(
        detail(plan), {"planned_start_date": "2026-09-30"}, format="json"
    )
    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.planned_start_date == date(2026, 9, 30)
    for url in [listing(stage.project), detail(plan)]:
        assert tenant_client.put(url, DATES, format="json").status_code == 405
    assert tenant_client.delete(detail(plan)).status_code == 204
    assert not StagePlan.objects.filter(pk=plan.pk).exists()
    assert ProjectStage.objects.filter(pk=stage.pk).exists()


def test_flat_full_list_is_ordered_and_scoped(tenant_client, project):
    late = StagePlanFactory(stage=ProjectStageFactory(project=project, position=2))
    early = [
        StagePlanFactory(stage=ProjectStageFactory(project=project, position=1))
        for _ in range(26)
    ]
    ProjectStageFactory(
        project=project
    )  # An unplanned stage does not create an empty plan.
    StagePlanFactory(
        stage=ProjectStageFactory(
            project=ProjectFactory(organization=project.organization)
        )
    )
    StagePlanFactory()
    response = tenant_client.get(listing(project), {"page": 2, "page_size": 1})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert [p["id"] for p in response.json()] == [*[p.pk for p in early], late.pk]
    assert all(set(p) == FIELDS for p in response.json())
    assert "no-store" in response["Cache-Control"]


def test_payload_cannot_choose_context_or_change_stage(tenant_client, stage):
    other = ProjectStageFactory()
    extras = {
        "project": other.project_id,
        "project_id": other.project_id,
        "organization": other.project.organization_id,
        "organization_id": other.project.organization_id,
        "stage": other.pk,
    }
    response = tenant_client.post(
        listing(stage.project), {"stage_id": stage.pk, **DATES, **extras}, format="json"
    )
    assert response.status_code == 201
    plan = StagePlan.objects.get(pk=response.json()["id"])
    same_project_stage = ProjectStageFactory(project=stage.project)
    for suggested_stage in [same_project_stage.pk, other.pk, None]:
        response = tenant_client.patch(
            detail(plan), {"stage_id": suggested_stage, **extras}, format="json"
        )
        assert response.status_code == 200
        plan.refresh_from_db()
        assert plan.stage_id == stage.pk
        assert plan.stage.project_id == stage.project_id


@pytest.mark.parametrize(
    "field", ["stage_id", "planned_start_date", "planned_end_date"]
)
@pytest.mark.parametrize("missing", [True, False])
def test_create_requires_stage_and_dates(tenant_client, stage, field, missing):
    payload = {"stage_id": stage.pk, **DATES}
    if missing:
        del payload[field]
    else:
        payload[field] = None
    response = tenant_client.post(listing(stage.project), payload, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert not StagePlan.objects.exists()


def test_invalid_dates_leave_existing_plan_unchanged(tenant_client, stage):
    response = tenant_client.post(
        listing(stage.project),
        {
            "stage_id": stage.pk,
            "planned_start_date": "2026-10-20",
            "planned_end_date": "2026-10-10",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "planned_end_date" in response.json()
    assert not StagePlan.objects.exists()
    plan = StagePlanFactory(stage=stage)
    before = StagePlan.objects.values().get(pk=plan.pk)
    for payload in [
        {"planned_start_date": "2026-10-21"},
        {"planned_end_date": "2026-09-30"},
        {"planned_start_date": None},
        {"planned_end_date": None},
        {"planned_start_date": "invalid"},
    ]:
        assert (
            tenant_client.patch(detail(plan), payload, format="json").status_code == 400
        )
    plan.refresh_from_db()
    assert StagePlan.objects.values().get(pk=plan.pk) == before


def test_duplicate_post_is_400_and_does_not_overwrite(tenant_client, stage):
    plan = StagePlanFactory(stage=stage)
    before = StagePlan.objects.values().get(pk=plan.pk)
    response = tenant_client.post(
        listing(stage.project), {"stage_id": stage.pk, **DATES}, format="json"
    )
    assert response.status_code == 400
    assert response.json() == {"stage_id": ["A etapa já possui planejamento."]}
    plan.refresh_from_db()
    assert StagePlan.objects.count() == 1
    assert StagePlan.objects.values().get(pk=plan.pk) == before


def test_stage_lookup_does_not_reveal_cross_project_or_tenant(tenant_client, project):
    other = ProjectStageFactory(
        project=ProjectFactory(organization=project.organization)
    )
    foreign = ProjectStageFactory()
    StagePlanFactory(stage=other)
    StagePlanFactory(stage=foreign)
    before = list(StagePlan.objects.order_by("pk").values())
    for stage_id in [other.pk, foreign.pk, 9223372036854775807]:
        response = tenant_client.post(
            listing(project), {"stage_id": stage_id, **DATES}, format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"stage_id": ["Etapa indisponível."]}
    assert list(StagePlan.objects.order_by("pk").values()) == before


@pytest.mark.parametrize(
    "method,collection",
    [
        ("get", True),
        ("post", True),
        ("get", False),
        ("patch", False),
        ("delete", False),
    ],
)
def test_foreign_project_is_404_without_changes(tenant_client, method, collection):
    plan = StagePlanFactory()
    before = StagePlan.objects.values().get(pk=plan.pk)
    url = listing(plan.stage.project) if collection else detail(plan)
    response = getattr(tenant_client, method)(
        url, {"stage_id": plan.stage_id, **DATES}, format="json"
    )
    assert response.status_code == 404
    plan.refresh_from_db()
    assert StagePlan.objects.values().get(pk=plan.pk) == before
    assert StagePlan.objects.count() == 1


@pytest.mark.parametrize("same_tenant", [True, False])
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_plan_from_other_project_is_404(tenant_client, project, same_tenant, method):
    other = (
        ProjectFactory(organization=project.organization)
        if same_tenant
        else ProjectFactory()
    )
    plan = StagePlanFactory(stage=ProjectStageFactory(project=other))
    before = StagePlan.objects.values().get(pk=plan.pk)
    response = getattr(tenant_client, method)(
        f"{listing(project)}{plan.pk}/", DATES, format="json"
    )
    assert response.status_code == 404
    plan.refresh_from_db()
    assert StagePlan.objects.values().get(pk=plan.pk) == before


def test_dates_are_independent_of_project_parent_and_children(tenant_client, stage):
    project = stage.project
    project.planned_start_date = date(2026, 10, 1)
    project.planned_end_date = date(2026, 10, 20)
    project.save()
    child = ProjectStageFactory(project=project, parent=stage)
    parent_plan = StagePlanFactory(stage=stage)
    dates = {"planned_start_date": "2025-01-01", "planned_end_date": "2028-12-31"}
    response = tenant_client.post(
        listing(project), {"stage_id": child.pk, **dates}, format="json"
    )
    assert response.status_code == 201
    child_plan = StagePlan.objects.get(pk=response.json()["id"])
    assert (
        tenant_client.patch(
            detail(parent_plan), {"planned_end_date": "2026-10-01"}, format="json"
        ).status_code
        == 200
    )
    child_plan.refresh_from_db()
    project.refresh_from_db()
    assert child_plan.planned_start_date == date(2025, 1, 1)
    assert child_plan.planned_end_date == date(2028, 12, 31)
    assert project.planned_end_date == date(2026, 10, 20)


@pytest.mark.parametrize("superuser", [False, True])
def test_member_reads_but_cannot_write_even_as_superuser(
    tenant_client, membership, stage, user, superuser
):
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    plan = StagePlanFactory(stage=stage)
    unplanned = ProjectStageFactory(project=stage.project)
    before = StagePlan.objects.values().get(pk=plan.pk)
    for url in [listing(stage.project), detail(plan)]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(url).status_code == 200
    assert (
        tenant_client.post(
            listing(stage.project), {"stage_id": unplanned.pk, **DATES}, format="json"
        ).status_code
        == 403
    )
    assert (
        tenant_client.patch(
            detail(plan), {"planned_end_date": "2026-10-01"}, format="json"
        ).status_code
        == 403
    )
    assert tenant_client.delete(detail(plan)).status_code == 403
    plan.refresh_from_db()
    assert StagePlan.objects.count() == 1
    assert StagePlan.objects.values().get(pk=plan.pk) == before


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_writes_require_csrf(tenant_client, stage, method):
    plan = StagePlanFactory(stage=stage)
    unplanned = ProjectStageFactory(project=stage.project)
    before = StagePlan.objects.values().get(pk=plan.pk)
    tenant_client.credentials()
    response = getattr(tenant_client, method)(
        listing(stage.project) if method == "post" else detail(plan),
        {"stage_id": unplanned.pk, **DATES},
        format="json",
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
    plan.refresh_from_db()
    assert StagePlan.objects.count() == 1
    assert StagePlan.objects.values().get(pk=plan.pk) == before


def test_missing_context_and_revocation_deny_access(
    authenticated_client, stage, membership
):
    plan = StagePlanFactory(stage=stage)
    anonymous = APIClient(enforce_csrf_checks=True)
    for client in [anonymous, authenticated_client]:
        assert client.get(listing(stage.project)).status_code == 403
        assert client.get(detail(plan)).status_code == 403
        assert (
            client.post(
                listing(stage.project), {"stage_id": stage.pk, **DATES}, format="json"
            ).status_code
            == 403
        )
    assert (
        authenticated_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert authenticated_client.get(listing(stage.project)).status_code == 403
    assert "current_organization_id" not in authenticated_client.session


def test_switching_tenant_changes_access(tenant_client, stage, user):
    first = StagePlanFactory(stage=stage)
    other = MembershipFactory(user=user, role=MembershipRole.OWNER)
    other_stage = ProjectStageFactory(
        project=ProjectFactory(organization=other.organization)
    )
    second = StagePlanFactory(stage=other_stage)
    assert tenant_client.get(detail(first)).status_code == 200
    assert tenant_client.get(listing(other_stage.project)).status_code == 404
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": other.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(detail(first)).status_code == 404
    assert [
        p["id"] for p in tenant_client.get(listing(other_stage.project)).json()
    ] == [second.pk]


@pytest.mark.parametrize("target", ["stage", "project"])
def test_existing_deletion_apis_cascade_to_planning(tenant_client, stage, target):
    plan = StagePlanFactory(stage=stage)
    foreign = StagePlanFactory()
    project_id = stage.project_id
    if target == "stage":
        url = f"/api/v1/projects/{project_id}/stages/{stage.pk}/"
    else:
        child = ProjectStageFactory(project=stage.project, parent=stage)
        StagePlanFactory(stage=child)
        url = f"/api/v1/projects/{project_id}/"
    assert tenant_client.delete(url).status_code == 204
    assert not ProjectStage.objects.filter(pk=stage.pk).exists()
    assert not StagePlan.objects.filter(pk=plan.pk).exists()
    assert StagePlan.objects.get() == foreign
    assert Project.objects.filter(pk=project_id).exists() == (target == "stage")
