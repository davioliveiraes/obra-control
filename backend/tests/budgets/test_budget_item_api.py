from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
FIELDS = {
    "id",
    "stage_id",
    "description",
    "unit",
    "quantity",
    "unit_price",
    "total",
    "created_at",
    "updated_at",
}
PAYLOAD = {
    "description": "Concreto FCK 30 MPa",
    "unit": "m³",
    "quantity": "25.0000",
    "unit_price": "520.00",
}


def listing(project):
    return f"/api/v1/projects/{project.pk}/budget/items/"


def detail(item):
    return f"{listing(item.stage.project)}{item.pk}/"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_crud_and_move_within_project_preserve_planning(
    tenant_client, membership, stage, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    plan = StagePlanFactory(stage=stage)
    plan_before = StagePlan.objects.values().get(pk=plan.pk)
    assert tenant_client.get(listing(stage.project)).json() == []
    response = tenant_client.post(
        listing(stage.project), {"stage_id": stage.pk, **PAYLOAD}, format="json"
    )
    assert response.status_code == 201
    assert set(response.json()) == FIELDS
    assert response.json()["total"] == "13000.00"
    item = BudgetItem.objects.get(pk=response.json()["id"])
    assert item.stage == stage
    assert item.quantity == Decimal("25.0000") and item.unit_price == Decimal("520.00")
    assert tenant_client.get(detail(item)).json() == response.json()
    other_stage = ProjectStageFactory(project=stage.project)
    response = tenant_client.patch(
        detail(item),
        {
            "stage_id": other_stage.pk,
            "description": "  Outro item  ",
            "unit": " un ",
            "quantity": "2.5000",
            "unit_price": "10.00",
        },
        format="json",
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.stage == other_stage
    assert item.description == "Outro item" and item.unit == "un"
    assert response.json()["total"] == "25.00"
    assert item.updated_at > item.created_at
    response = tenant_client.patch(detail(item), {"unit_price": "0.00"}, format="json")
    assert response.status_code == 200 and response.json()["total"] == "0.00"
    item.refresh_from_db()
    assert item.stage_id == other_stage.pk and item.quantity == Decimal("2.5000")
    for url in [listing(stage.project), detail(item)]:
        assert tenant_client.put(url, PAYLOAD, format="json").status_code == 405
    assert tenant_client.delete(detail(item)).status_code == 204
    assert not BudgetItem.objects.filter(pk=item.pk).exists()
    assert ProjectStage.objects.filter(pk__in=[stage.pk, other_stage.pk]).count() == 2
    plan.refresh_from_db()
    assert StagePlan.objects.values().get(pk=plan.pk) == plan_before


def test_flat_full_collection_is_ordered_and_isolated(tenant_client, project):
    first_stage = ProjectStageFactory(project=project)
    second_stage = ProjectStageFactory(project=project)
    later = BudgetItemFactory(stage=second_stage)
    earlier = BudgetItemFactory.create_batch(26, stage=first_stage)
    BudgetItemFactory(
        stage=ProjectStageFactory(
            project=ProjectFactory(organization=project.organization)
        )
    )
    BudgetItemFactory()
    response = tenant_client.get(listing(project), {"page": 2, "page_size": 1})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert [row["id"] for row in response.json()] == [
        *[i.pk for i in earlier],
        later.pk,
    ]
    assert all(set(row) == FIELDS for row in response.json())
    assert "no-store" in response["Cache-Control"]


def test_payload_cannot_set_total_or_context(tenant_client, stage):
    foreign = ProjectStageFactory()
    extras = {
        "project": foreign.project_id,
        "project_id": foreign.project_id,
        "organization": foreign.project.organization_id,
        "organization_id": foreign.project.organization_id,
        "stage": foreign.pk,
        "total": "999999.99",
    }
    response = tenant_client.post(
        listing(stage.project),
        {
            **PAYLOAD,
            "quantity": "2.0000",
            "unit_price": "10.00",
            "stage_id": stage.pk,
            **extras,
        },
        format="json",
    )
    assert response.status_code == 201 and response.json()["total"] == "20.00"
    item = BudgetItem.objects.get(pk=response.json()["id"])
    assert item.stage_id == stage.pk
    response = tenant_client.patch(
        detail(item), {**extras, "quantity": "3.0000"}, format="json"
    )
    assert response.status_code == 200 and response.json()["total"] == "30.00"
    item.refresh_from_db()
    assert item.stage_id == stage.pk
    assert item.total == Decimal("30.000000")
    assert not StagePlan.objects.exists()


@pytest.mark.parametrize(
    "field", ["stage_id", "description", "unit", "quantity", "unit_price"]
)
def test_create_requires_all_input_fields(tenant_client, stage, field):
    payload = {"stage_id": stage.pk, **PAYLOAD}
    del payload[field]
    response = tenant_client.post(listing(stage.project), payload, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not BudgetItem.objects.exists()


@pytest.mark.parametrize(
    "field,values",
    [
        ("description", [None, "", "   ", "x" * 256]),
        ("unit", [None, "", "   ", "x" * 21]),
        (
            "quantity",
            [
                None,
                "0",
                "-1",
                "-0.0001",
                "0.00001",
                "1.00001",
                "10000000000.0000",
                "NaN",
                "sNaN",
                "Infinity",
                "-Infinity",
                "not-a-number",
            ],
        ),
        (
            "unit_price",
            [
                None,
                "-0.01",
                "0.001",
                "1000000000000.00",
                "NaN",
                "sNaN",
                "Infinity",
                "-Infinity",
                "not-a-number",
            ],
        ),
        ("stage_id", [None, "invalid", 0]),
    ],
)
def test_invalid_fields_rejected_on_create_and_patch_without_changes(
    tenant_client, stage, field, values
):
    item = BudgetItemFactory(stage=stage)
    before = BudgetItem.objects.values().get(pk=item.pk)
    for value in values:
        response = tenant_client.post(
            listing(stage.project),
            {"stage_id": stage.pk, **PAYLOAD, field: value},
            format="json",
        )
        assert response.status_code == 400 and field in response.json()
        response = tenant_client.patch(detail(item), {field: value}, format="json")
        assert response.status_code == 400 and field in response.json()
    item.refresh_from_db()
    assert BudgetItem.objects.count() == 1
    assert BudgetItem.objects.values().get(pk=item.pk) == before


@pytest.mark.parametrize(
    "quantity,price,total",
    [
        ("0.0001", "0.00", "0.00"),
        ("1", "0.01", "0.01"),
        ("1.5", "1000.00", "1500.00"),
        ("1000.1234", "1.00", "1000.12"),
        ("0.3333", "3.00", "1.00"),
        ("1.0050", "1.00", "1.01"),
        ("9999999999.9999", "999999999999.99", "9999999999999800000000.00"),
    ],
)
def test_decimal_http_round_trip(tenant_client, stage, quantity, price, total):
    response = tenant_client.post(
        listing(stage.project),
        {"stage_id": stage.pk, **PAYLOAD, "quantity": quantity, "unit_price": price},
        format="json",
    )
    assert response.status_code == 201
    item = BudgetItem.objects.get(pk=response.json()["id"])
    assert isinstance(item.quantity, Decimal) and isinstance(item.unit_price, Decimal)
    assert item.quantity == Decimal(quantity) and item.unit_price == Decimal(price)
    assert isinstance(item.total, Decimal)
    assert response.json()["quantity"] == format(Decimal(quantity), ".4f")
    assert response.json()["unit_price"] == format(Decimal(price), ".2f")
    assert response.json()["total"] == total
    assert tenant_client.get(detail(item)).json()["total"] == total


@pytest.mark.parametrize("method", ["post", "patch"])
def test_stage_outside_project_is_rejected_without_existence_leak(
    tenant_client, project, method
):
    item = BudgetItemFactory(stage=ProjectStageFactory(project=project))
    other = ProjectStageFactory(
        project=ProjectFactory(organization=project.organization)
    )
    foreign = ProjectStageFactory()
    before = BudgetItem.objects.values().get(pk=item.pk)
    for stage_id in [other.pk, foreign.pk, 9223372036854775807]:
        response = getattr(tenant_client, method)(
            listing(project) if method == "post" else detail(item),
            {"stage_id": stage_id, **PAYLOAD},
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {"stage_id": ["Etapa indisponível."]}
    item.refresh_from_db()
    assert BudgetItem.objects.count() == 1
    assert BudgetItem.objects.values().get(pk=item.pk) == before


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
def test_foreign_project_is_404(tenant_client, method, collection):
    item = BudgetItemFactory()
    before = BudgetItem.objects.values().get(pk=item.pk)
    response = getattr(tenant_client, method)(
        listing(item.stage.project) if collection else detail(item),
        {"stage_id": item.stage_id, **PAYLOAD},
        format="json",
    )
    assert response.status_code == 404
    item.refresh_from_db()
    assert BudgetItem.objects.values().get(pk=item.pk) == before
    assert BudgetItem.objects.count() == 1


@pytest.mark.parametrize("same_tenant", [True, False])
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_foreign_item_under_local_project_route_is_404(
    tenant_client, project, same_tenant, method
):
    other = (
        ProjectFactory(organization=project.organization)
        if same_tenant
        else ProjectFactory()
    )
    item = BudgetItemFactory(stage=ProjectStageFactory(project=other))
    before = BudgetItem.objects.values().get(pk=item.pk)
    response = getattr(tenant_client, method)(
        f"{listing(project)}{item.pk}/", PAYLOAD, format="json"
    )
    assert response.status_code == 404
    item.refresh_from_db()
    assert BudgetItem.objects.values().get(pk=item.pk) == before


@pytest.mark.parametrize("superuser", [False, True])
def test_member_reads_but_cannot_write_even_as_superuser(
    tenant_client, membership, stage, user, superuser
):
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    item = BudgetItemFactory(stage=stage)
    before = BudgetItem.objects.values().get(pk=item.pk)
    for url in [listing(stage.project), detail(item)]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(url).status_code == 200
    assert (
        tenant_client.post(
            listing(stage.project), {"stage_id": stage.pk, **PAYLOAD}, format="json"
        ).status_code
        == 403
    )
    assert tenant_client.patch(detail(item), PAYLOAD, format="json").status_code == 403
    assert tenant_client.delete(detail(item)).status_code == 403
    item.refresh_from_db()
    assert BudgetItem.objects.count() == 1
    assert BudgetItem.objects.values().get(pk=item.pk) == before


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_unsafe_methods_require_csrf(tenant_client, stage, method):
    item = BudgetItemFactory(stage=stage)
    before = BudgetItem.objects.values().get(pk=item.pk)
    tenant_client.credentials()
    response = getattr(tenant_client, method)(
        listing(stage.project) if method == "post" else detail(item),
        {"stage_id": stage.pk, **PAYLOAD},
        format="json",
    )
    assert response.status_code == 403 and "CSRF" in response.json()["detail"]
    item.refresh_from_db()
    assert BudgetItem.objects.count() == 1
    assert BudgetItem.objects.values().get(pk=item.pk) == before


def test_anonymous_missing_context_and_revoked_membership_are_denied(
    authenticated_client, membership, stage
):
    item = BudgetItemFactory(stage=stage)
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        assert client.get(listing(stage.project)).status_code == 403
        assert client.get(detail(item)).status_code == 403
        assert (
            client.post(
                listing(stage.project), {"stage_id": stage.pk, **PAYLOAD}, format="json"
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


def test_switching_organization_changes_visible_items(tenant_client, stage, user):
    first = BudgetItemFactory(stage=stage)
    other = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = BudgetItemFactory(
        stage=ProjectStageFactory(
            project=ProjectFactory(organization=other.organization)
        )
    )
    assert tenant_client.get(detail(first)).status_code == 200
    assert tenant_client.get(detail(second)).status_code == 404
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
        i["id"] for i in tenant_client.get(listing(second.stage.project)).json()
    ] == [second.pk]


def test_planning_crud_does_not_change_budget(tenant_client, stage):
    item = BudgetItemFactory(stage=stage)
    before = BudgetItem.objects.values().get(pk=item.pk)
    url = f"/api/v1/projects/{stage.project_id}/planning/"
    response = tenant_client.post(
        url,
        {
            "stage_id": stage.pk,
            "planned_start_date": "2026-10-01",
            "planned_end_date": "2026-10-20",
        },
        format="json",
    )
    assert response.status_code == 201
    plan_url = f"{url}{response.json()['id']}/"
    assert (
        tenant_client.patch(
            plan_url, {"planned_end_date": "2026-10-30"}, format="json"
        ).status_code
        == 200
    )
    assert tenant_client.delete(plan_url).status_code == 204
    item.refresh_from_db()
    assert BudgetItem.objects.values().get(pk=item.pk) == before
    assert ProjectStage.objects.filter(pk=stage.pk).exists()


@pytest.mark.parametrize("target", ["stage", "project"])
def test_existing_deletion_cascades_preserve_external_data(
    tenant_client, stage, target
):
    item = BudgetItemFactory(stage=stage)
    StagePlanFactory(stage=stage)
    foreign = BudgetItemFactory()
    project_id = stage.project_id
    if target == "stage":
        url = f"/api/v1/projects/{project_id}/stages/{stage.pk}/"
    else:
        child = ProjectStageFactory(project=stage.project, parent=stage)
        BudgetItemFactory(stage=child)
        StagePlanFactory(stage=child)
        assert (
            tenant_client.delete(
                f"/api/v1/projects/{project_id}/stages/{stage.pk}/"
            ).status_code
            == 409
        )
        assert BudgetItem.objects.filter(stage__project_id=project_id).count() == 2
        url = f"/api/v1/projects/{project_id}/"
    assert tenant_client.delete(url).status_code == 204
    assert not BudgetItem.objects.filter(pk=item.pk).exists()
    assert not ProjectStage.objects.filter(pk=stage.pk).exists()
    assert not StagePlan.objects.filter(stage__project_id=project_id).exists()
    assert BudgetItem.objects.get() == foreign
    assert Project.objects.filter(pk=project_id).exists() == (target == "stage")
