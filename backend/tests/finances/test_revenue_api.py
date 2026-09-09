from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.finances.models import Expense, Revenue, RevenueStatus
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
PAYLOAD = {
    "description": "Parcela recebida do contrato",
    "amount": "50000.00",
    "revenue_date": "2026-09-05",
}
FIELDS = {
    "id",
    "description",
    "amount",
    "revenue_date",
    "status",
    "notes",
    "created_at",
    "updated_at",
}


def listing(project):
    return f"/api/v1/projects/{project.pk}/revenues/"


def detail(revenue):
    return f"{listing(revenue.project)}{revenue.pk}/"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_create_edit_cancel_and_no_hard_delete(
    tenant_client, membership, project, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    response = tenant_client.post(listing(project), PAYLOAD, format="json")
    assert response.status_code == 201 and set(response.json()) == FIELDS
    assert response.json()["status"] == "active" and response.json()["notes"] == ""
    assert response.json()["amount"] == "50000.00"
    revenue = Revenue.objects.get(pk=response.json()["id"])
    assert revenue.project == project
    assert tenant_client.get(detail(revenue)).json() == response.json()
    response = tenant_client.patch(
        detail(revenue),
        {
            "description": "  Entrada conferida  ",
            "amount": "1000000.99",
            "revenue_date": "2026-09-06",
            "notes": "Transferência bancária",
        },
        format="json",
    )
    assert response.status_code == 200
    revenue.refresh_from_db()
    assert revenue.description == "Entrada conferida"
    assert revenue.amount == Decimal("1000000.99")
    assert revenue.revenue_date == date(2026, 9, 6)
    assert revenue.notes == "Transferência bancária"
    assert revenue.updated_at > revenue.created_at
    before = Revenue.objects.values().get(pk=revenue.pk)
    response = tenant_client.patch(
        detail(revenue), {"status": "canceled"}, format="json"
    )
    assert response.status_code == 200
    revenue.refresh_from_db()
    assert Revenue.objects.values().get(pk=revenue.pk) == {
        **before,
        "status": "canceled",
        "updated_at": revenue.updated_at,
    }
    response = tenant_client.patch(
        detail(revenue), {"notes": "Conferido"}, format="json"
    )
    assert response.status_code == 200 and response.json()["status"] == "canceled"
    for url in [listing(project), detail(revenue)]:
        for method in ["put", "delete"]:
            assert (
                getattr(tenant_client, method)(url, PAYLOAD, format="json").status_code
                == 405
            )
    revenue.refresh_from_db()
    assert Revenue.objects.count() == 1 and revenue.status == RevenueStatus.CANCELED
    assert revenue.project == project and revenue.amount == Decimal("1000000.99")


def test_payload_cannot_move_revenue_or_add_stage_customer_tenant(
    tenant_client, project
):
    foreign = ProjectStageFactory()
    extras = {
        "project": foreign.project_id,
        "project_id": foreign.project_id,
        "organization": foreign.project.organization_id,
        "organization_id": foreign.project.organization_id,
        "stage": foreign.pk,
        "stage_id": foreign.pk,
        "customer_id": 123,
    }
    response = tenant_client.post(
        listing(project), {**PAYLOAD, **extras}, format="json"
    )
    assert response.status_code == 201 and set(response.json()) == FIELDS
    revenue = Revenue.objects.get(pk=response.json()["id"])
    assert revenue.project == project
    response = tenant_client.patch(
        detail(revenue), {**extras, "notes": "Ajuste"}, format="json"
    )
    assert response.status_code == 200
    revenue.refresh_from_db()
    assert revenue.project == project and revenue.notes == "Ajuste"


def test_listing_is_scoped_paginated_and_deterministic_including_canceled(
    tenant_client, project
):
    older = RevenueFactory(project=project, revenue_date=date(2026, 9, 1))
    same_day = RevenueFactory.create_batch(
        25, project=project, revenue_date=date(2026, 9, 2)
    )
    newest = RevenueFactory(
        project=project, revenue_date=date(2026, 9, 3), status=RevenueStatus.CANCELED
    )
    RevenueFactory(project=ProjectFactory(organization=project.organization))
    RevenueFactory()
    response = tenant_client.get(
        listing(project), {"page_size": 10000, "ordering": "id", "status": "active"}
    )
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    data = response.json()
    assert set(data) == {"count", "next", "previous", "results"}
    assert (
        data["count"] == 27 and len(data["results"]) == 25 and data["next"] is not None
    )
    page2 = tenant_client.get(listing(project), {"page": 2}).json()
    assert page2["next"] is None and page2["previous"] is not None
    assert [r["id"] for r in data["results"] + page2["results"]] == [
        newest.pk,
        *[r.pk for r in reversed(same_day)],
        older.pk,
    ]


@pytest.mark.parametrize("field", ["description", "amount", "revenue_date"])
def test_create_requires_domain_fields(tenant_client, project, field):
    payload = PAYLOAD.copy()
    del payload[field]
    response = tenant_client.post(listing(project), payload, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not Revenue.objects.exists()


@pytest.mark.parametrize(
    "field,values",
    [
        ("description", [None, "", "   ", "x" * 256]),
        (
            "amount",
            [
                None,
                "0",
                "0.00",
                "-0.01",
                "-100",
                "0.001",
                "1000000000000.00",
                "NaN",
                "sNaN",
                "Infinity",
                "-Infinity",
                "invalid",
            ],
        ),
        ("revenue_date", [None, "", "invalid", "2026-02-30"]),
        ("status", [None, "", "paid", "pending", "overdue", "receivable"]),
    ],
)
def test_invalid_fields_rejected_before_database_create_or_patch(
    tenant_client, project, field, values
):
    revenue = RevenueFactory(project=project)
    before = Revenue.objects.values().get(pk=revenue.pk)
    for value in values:
        for method, url in [("post", listing(project)), ("patch", detail(revenue))]:
            response = getattr(tenant_client, method)(
                url, {**PAYLOAD, field: value}, format="json"
            )
            assert response.status_code == 400 and field in response.json()
    revenue.refresh_from_db()
    assert Revenue.objects.count() == 1
    assert Revenue.objects.values().get(pk=revenue.pk) == before


@pytest.mark.parametrize("amount", ["0.01", "10.00", "1000000.99", "999999999999.99"])
def test_decimal_roundtrip_with_boundary_values(tenant_client, project, amount):
    response = tenant_client.post(
        listing(project), {**PAYLOAD, "amount": amount}, format="json"
    )
    assert response.status_code == 201 and response.json()["amount"] == amount
    revenue = Revenue.objects.get(pk=response.json()["id"])
    assert isinstance(revenue.amount, Decimal) and revenue.amount == Decimal(amount)
    assert tenant_client.get(detail(revenue)).json()["amount"] == amount


@pytest.mark.parametrize(
    "method,collection",
    [("get", True), ("post", True), ("get", False), ("patch", False)],
)
def test_foreign_project_is_indistinguishable_from_missing(
    tenant_client, method, collection
):
    revenue = RevenueFactory()
    before = Revenue.objects.values().get(pk=revenue.pk)
    target = listing(revenue.project) if collection else detail(revenue)
    missing = "/api/v1/projects/9223372036854775807/revenues/"
    if not collection:
        missing += f"{revenue.pk}/"
    response = getattr(tenant_client, method)(target, {}, format="json")
    absent = getattr(tenant_client, method)(missing, {}, format="json")
    assert response.status_code == absent.status_code == 404
    assert response.json() == absent.json()
    revenue.refresh_from_db()
    assert (
        Revenue.objects.count() == 1
        and Revenue.objects.values().get(pk=revenue.pk) == before
    )


@pytest.mark.parametrize("same_tenant", [False, True])
@pytest.mark.parametrize("method", ["get", "patch"])
def test_foreign_revenue_under_local_project_route_returns_404(
    tenant_client, project, same_tenant, method
):
    other = (
        ProjectFactory(organization=project.organization)
        if same_tenant
        else ProjectFactory()
    )
    revenue = RevenueFactory(project=other)
    before = Revenue.objects.values().get(pk=revenue.pk)
    response = getattr(tenant_client, method)(
        f"{listing(project)}{revenue.pk}/", PAYLOAD, format="json"
    )
    missing = getattr(tenant_client, method)(
        f"{listing(project)}9223372036854775807/", PAYLOAD, format="json"
    )
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    revenue.refresh_from_db()
    assert Revenue.objects.values().get(pk=revenue.pk) == before


@pytest.mark.parametrize("superuser", [False, True])
def test_member_read_only_even_when_superuser(
    tenant_client, membership, project, user, superuser
):
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    revenue = RevenueFactory(project=project)
    before = Revenue.objects.values().get(pk=revenue.pk)
    for url in [listing(project), detail(revenue)]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(url).status_code == 200
    assert tenant_client.get(detail(RevenueFactory())).status_code == 404
    count = Revenue.objects.count()
    assert (
        tenant_client.post(listing(project), PAYLOAD, format="json").status_code == 403
    )
    assert (
        tenant_client.patch(
            detail(revenue), {"status": "canceled"}, format="json"
        ).status_code
        == 403
    )
    # DRF checks role permissions before dispatching unsupported unsafe methods.
    assert tenant_client.delete(detail(revenue)).status_code == 403
    revenue.refresh_from_db()
    assert (
        Revenue.objects.count() == count
        and Revenue.objects.values().get(pk=revenue.pk) == before
    )


@pytest.mark.parametrize("method", ["post", "patch"])
def test_writing_without_real_csrf_is_rejected(tenant_client, project, method):
    revenue = RevenueFactory(project=project)
    before = Revenue.objects.values().get(pk=revenue.pk)
    tenant_client.credentials()
    response = getattr(tenant_client, method)(
        listing(project) if method == "post" else detail(revenue),
        PAYLOAD,
        format="json",
    )
    assert response.status_code == 403 and "CSRF" in response.json()["detail"]
    revenue.refresh_from_db()
    assert (
        Revenue.objects.count() == 1
        and Revenue.objects.values().get(pk=revenue.pk) == before
    )


def test_anonymous_no_context_and_revocation_are_denied(
    authenticated_client, membership, project
):
    revenue = RevenueFactory(project=project)
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        for method, url in [
            ("get", listing(project)),
            ("get", detail(revenue)),
            ("post", listing(project)),
            ("patch", detail(revenue)),
        ]:
            assert (
                getattr(client, method)(url, PAYLOAD, format="json").status_code == 403
            )
    assert (
        authenticated_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": project.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert authenticated_client.get(listing(project)).status_code == 200
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert authenticated_client.get(listing(project)).status_code == 403
    assert "current_organization_id" not in authenticated_client.session


def test_switching_organization_changes_visible_revenues(tenant_client, project, user):
    first = RevenueFactory(project=project)
    membership = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = RevenueFactory(
        project=ProjectFactory(organization=membership.organization)
    )
    assert tenant_client.get(detail(first)).status_code == 200
    assert tenant_client.get(detail(second)).status_code == 404
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(detail(first)).status_code == 404
    assert (
        tenant_client.get(listing(second.project)).json()["results"][0]["id"]
        == second.pk
    )


@pytest.mark.parametrize("status", RevenueStatus.values)
@pytest.mark.parametrize("with_expense", [False, True])
def test_project_protection_returns_409_without_partial_deletes(
    tenant_client, stage, status, with_expense
):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    RevenueFactory(project=stage.project, status=status)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    if with_expense:
        ExpenseFactory(project=stage.project, stage=child)
    models = [Project, ProjectStage, Revenue, Expense, BudgetItem, StagePlan]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    response = tenant_client.delete(f"/api/v1/projects/{stage.project_id}/")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A obra possui registros vinculados e não pode ser excluída."
    }
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before


def test_project_without_financial_records_still_deletes(tenant_client, stage):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    external = RevenueFactory()
    assert (
        tenant_client.delete(f"/api/v1/projects/{stage.project_id}/").status_code == 204
    )
    assert not ProjectStage.objects.exists()
    assert not BudgetItem.objects.exists() and not StagePlan.objects.exists()
    external.refresh_from_db()


def test_revenue_never_changes_expense_budget_planning_or_cost_summary(
    tenant_client, stage
):
    BudgetItemFactory(stage=stage, unit_price=Decimal("1000.00"))
    ExpenseFactory(project=stage.project, stage=stage, amount=Decimal("700.00"))
    StagePlanFactory(stage=stage)
    summary_url = f"/api/v1/projects/{stage.project_id}/cost-summary/"
    before = tenant_client.get(summary_url).json()
    assert before["budget_total"] == "1000.00" and before["actual_total"] == "700.00"
    assert before["variance_amount"] == "300.00"
    models = [Expense, BudgetItem, StagePlan]
    sources = {model: list(model.objects.order_by("pk").values()) for model in models}
    response = tenant_client.post(listing(stage.project), PAYLOAD, format="json")
    assert response.status_code == 201
    revenue = Revenue.objects.get(pk=response.json()["id"])
    assert tenant_client.get(summary_url).json() == before
    for payload in [{"amount": "999999999999.99"}, {"status": "canceled"}]:
        assert (
            tenant_client.patch(detail(revenue), payload, format="json").status_code
            == 200
        )
        assert tenant_client.get(summary_url).json() == before
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == sources
