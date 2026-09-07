from datetime import date
from decimal import Decimal

import pytest
from django.db.models.deletion import ProtectedError
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.finances.models import Expense, ExpenseStatus
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
PAYLOAD = {
    "description": "Compra de concreto",
    "amount": "8750.40",
    "expense_date": "2026-09-06",
}
FIELDS = {
    "id",
    "stage_id",
    "description",
    "amount",
    "expense_date",
    "status",
    "notes",
    "created_at",
    "updated_at",
}


def listing(project):
    return f"/api/v1/projects/{project.pk}/expenses/"


def detail(expense):
    return f"{listing(expense.project)}{expense.pk}/"


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_create_update_cancel_preserves_budget_planning_and_financial_record(
    tenant_client, membership, stage, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    budget = BudgetItemFactory(stage=stage)
    plan = StagePlanFactory(stage=stage)
    budget_before = BudgetItem.objects.values().get(pk=budget.pk)
    plan_before = StagePlan.objects.values().get(pk=plan.pk)
    response = tenant_client.post(
        listing(stage.project),
        {**PAYLOAD, "stage_id": stage.pk, "notes": "NF 12345"},
        format="json",
    )
    assert response.status_code == 201
    assert set(response.json()) == FIELDS
    expense = Expense.objects.get(pk=response.json()["id"])
    assert expense.project == stage.project and expense.stage == stage
    assert (
        response.json()["amount"] == "8750.40" and response.json()["status"] == "active"
    )
    assert tenant_client.get(detail(expense)).json() == response.json()
    other = ProjectStageFactory(project=stage.project)
    response = tenant_client.patch(
        detail(expense),
        {
            "stage_id": other.pk,
            "description": "  Ajuste  ",
            "amount": "0.01",
            "expense_date": "2026-09-07",
            "notes": "Conferido",
        },
        format="json",
    )
    assert response.status_code == 200
    expense.refresh_from_db()
    assert expense.stage == other and expense.description == "Ajuste"
    assert expense.amount == Decimal("0.01") and expense.expense_date == date(
        2026, 9, 7
    )
    assert expense.notes == "Conferido" and expense.updated_at > expense.created_at
    response = tenant_client.patch(
        detail(expense), {"status": "canceled"}, format="json"
    )
    assert response.status_code == 200
    expense.refresh_from_db()
    assert expense.status == ExpenseStatus.CANCELED
    assert expense.amount == Decimal("0.01") and expense.stage == other
    response = tenant_client.patch(
        detail(expense), {"notes": "Correção de observação"}, format="json"
    )
    assert response.status_code == 200 and response.json()["status"] == "canceled"
    assert (
        tenant_client.get(listing(stage.project)).json()["results"][0]["id"]
        == expense.pk
    )
    for url in [listing(stage.project), detail(expense)]:
        for method in ["delete", "put"]:
            assert (
                getattr(tenant_client, method)(url, PAYLOAD, format="json").status_code
                == 405
            )
    assert Expense.objects.filter(pk=expense.pk).exists()
    assert BudgetItem.objects.values().get(pk=budget.pk) == budget_before
    assert StagePlan.objects.values().get(pk=plan.pk) == plan_before


def test_general_expense_can_assign_replace_and_remove_stage(tenant_client, stage):
    # Stage may be omitted entirely on creation.
    response = tenant_client.post(listing(stage.project), PAYLOAD, format="json")
    assert response.status_code == 201 and response.json()["stage_id"] is None
    assert response.json()["notes"] == ""
    expense = Expense.objects.get(pk=response.json()["id"])
    other = ProjectStageFactory(project=stage.project)
    for stage_id in [stage.pk, other.pk, None]:
        response = tenant_client.patch(
            detail(expense), {"stage_id": stage_id}, format="json"
        )
        assert response.status_code == 200
        expense.refresh_from_db()
        assert expense.stage_id == stage_id and expense.project_id == stage.project_id
    response = tenant_client.post(
        listing(stage.project), {**PAYLOAD, "stage_id": None}, format="json"
    )
    assert response.status_code == 201 and response.json()["stage_id"] is None


def test_project_and_organization_payload_never_transfer_context(tenant_client, stage):
    foreign = ProjectStageFactory()
    extras = {
        "project": foreign.project_id,
        "project_id": foreign.project_id,
        "organization": foreign.project.organization_id,
        "organization_id": foreign.project.organization_id,
        "stage": foreign.pk,
    }
    response = tenant_client.post(
        listing(stage.project),
        {**PAYLOAD, **extras, "stage_id": stage.pk},
        format="json",
    )
    assert response.status_code == 201
    expense = Expense.objects.get(pk=response.json()["id"])
    assert expense.project_id == stage.project_id and expense.stage_id == stage.pk
    response = tenant_client.patch(
        detail(expense), {**extras, "notes": "Alterado"}, format="json"
    )
    assert response.status_code == 200
    expense.refresh_from_db()
    assert expense.project_id == stage.project_id and expense.stage_id == stage.pk


def test_list_is_paginated_ordered_and_scoped_including_canceled(
    tenant_client, project
):
    older = ExpenseFactory(project=project, expense_date=date(2026, 9, 1))
    same_date = ExpenseFactory.create_batch(
        25, project=project, expense_date=date(2026, 9, 2)
    )
    newest = ExpenseFactory(
        project=project, expense_date=date(2026, 9, 3), status=ExpenseStatus.CANCELED
    )
    ExpenseFactory(project=ProjectFactory(organization=project.organization))
    ExpenseFactory()
    response = tenant_client.get(
        listing(project), {"page_size": 10000, "ordering": "id", "status": "active"}
    )
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert (
        body["count"] == 27 and len(body["results"]) == 25 and body["next"] is not None
    )
    page2 = tenant_client.get(listing(project), {"page": 2}).json()
    assert page2["next"] is None and page2["previous"] is not None
    assert [row["id"] for row in body["results"] + page2["results"]] == [
        newest.pk,
        *[e.pk for e in reversed(same_date)],
        older.pk,
    ]


@pytest.mark.parametrize("field", ["description", "amount", "expense_date"])
def test_create_required_fields(tenant_client, project, field):
    payload = PAYLOAD.copy()
    del payload[field]
    response = tenant_client.post(listing(project), payload, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not Expense.objects.exists()


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
        ("expense_date", [None, "", "invalid", "2026-02-30"]),
        ("status", [None, "", "paid", "pending", "overdue"]),
        ("stage_id", ["invalid", 0, 2**63]),
    ],
)
def test_invalid_fields_create_patch_do_not_change_database(
    tenant_client, project, field, values
):
    expense = ExpenseFactory(project=project)
    before = Expense.objects.values().get(pk=expense.pk)
    for value in values:
        for method, url in [("post", listing(project)), ("patch", detail(expense))]:
            response = getattr(tenant_client, method)(
                url, {**PAYLOAD, field: value}, format="json"
            )
            assert response.status_code == 400 and field in response.json()
    expense.refresh_from_db()
    assert Expense.objects.count() == 1
    assert Expense.objects.values().get(pk=expense.pk) == before


@pytest.mark.parametrize("amount", ["0.01", "10.00", "1000000.99", "999999999999.99"])
def test_decimal_http_roundtrip(tenant_client, project, amount):
    response = tenant_client.post(
        listing(project), {**PAYLOAD, "amount": amount}, format="json"
    )
    assert response.status_code == 201 and response.json()["amount"] == amount
    expense = Expense.objects.get(pk=response.json()["id"])
    assert isinstance(expense.amount, Decimal) and expense.amount == Decimal(amount)
    assert tenant_client.get(detail(expense)).json()["amount"] == amount


@pytest.mark.parametrize("method", ["post", "patch"])
def test_foreign_stage_and_missing_stage_have_same_error(tenant_client, stage, method):
    expense = ExpenseFactory(project=stage.project, stage=stage)
    same_tenant = ProjectStageFactory(
        project=ProjectFactory(organization=stage.project.organization)
    )
    foreign = ProjectStageFactory()
    before = Expense.objects.values().get(pk=expense.pk)
    for stage_id in [same_tenant.pk, foreign.pk, 9223372036854775807]:
        response = getattr(tenant_client, method)(
            listing(stage.project) if method == "post" else detail(expense),
            {**PAYLOAD, "stage_id": stage_id},
            format="json",
        )
        assert response.status_code == 400
        assert response.json() == {"stage_id": ["Etapa indisponível."]}
    expense.refresh_from_db()
    assert (
        Expense.objects.count() == 1
        and Expense.objects.values().get(pk=expense.pk) == before
    )


@pytest.mark.parametrize(
    "method,collection",
    [("get", True), ("post", True), ("get", False), ("patch", False)],
)
def test_foreign_project_is_hidden(tenant_client, method, collection):
    expense = ExpenseFactory()
    before = Expense.objects.values().get(pk=expense.pk)
    response = getattr(tenant_client, method)(
        listing(expense.project) if collection else detail(expense),
        PAYLOAD,
        format="json",
    )
    assert response.status_code == 404
    expense.refresh_from_db()
    assert (
        Expense.objects.count() == 1
        and Expense.objects.values().get(pk=expense.pk) == before
    )


@pytest.mark.parametrize("same_tenant", [False, True])
@pytest.mark.parametrize("method", ["get", "patch"])
def test_foreign_expense_under_local_project_route_is_hidden(
    tenant_client, project, same_tenant, method
):
    other = (
        ProjectFactory(organization=project.organization)
        if same_tenant
        else ProjectFactory()
    )
    expense = ExpenseFactory(project=other)
    before = Expense.objects.values().get(pk=expense.pk)
    response = getattr(tenant_client, method)(
        f"{listing(project)}{expense.pk}/", PAYLOAD, format="json"
    )
    assert response.status_code == 404
    expense.refresh_from_db()
    assert Expense.objects.values().get(pk=expense.pk) == before


@pytest.mark.parametrize("superuser", [False, True])
def test_member_read_only_including_superuser(
    tenant_client, membership, project, user, superuser
):
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    expense = ExpenseFactory(project=project)
    before = Expense.objects.values().get(pk=expense.pk)
    for url in [listing(project), detail(expense)]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(url).status_code == 200
    assert (
        tenant_client.post(listing(project), PAYLOAD, format="json").status_code == 403
    )
    assert (
        tenant_client.patch(
            detail(expense), {"status": "canceled"}, format="json"
        ).status_code
        == 403
    )
    # DRF checks permissions before reporting unsupported unsafe methods.
    assert tenant_client.delete(detail(expense)).status_code == 403
    expense.refresh_from_db()
    assert (
        Expense.objects.count() == 1
        and Expense.objects.values().get(pk=expense.pk) == before
    )


@pytest.mark.parametrize("method", ["post", "patch"])
def test_writes_require_real_csrf(tenant_client, project, method):
    expense = ExpenseFactory(project=project)
    before = Expense.objects.values().get(pk=expense.pk)
    tenant_client.credentials()
    response = getattr(tenant_client, method)(
        listing(project) if method == "post" else detail(expense),
        PAYLOAD,
        format="json",
    )
    assert response.status_code == 403 and "CSRF" in response.json()["detail"]
    expense.refresh_from_db()
    assert (
        Expense.objects.count() == 1
        and Expense.objects.values().get(pk=expense.pk) == before
    )


def test_anonymous_missing_context_and_revoked_membership(
    authenticated_client, membership, project
):
    expense = ExpenseFactory(project=project)
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        assert client.get(listing(project)).status_code == 403
        assert client.get(detail(expense)).status_code == 403
        assert client.post(listing(project), PAYLOAD, format="json").status_code == 403
    assert (
        authenticated_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": project.organization_id},
            format="json",
        ).status_code
        == 200
    )
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert authenticated_client.get(listing(project)).status_code == 403
    assert "current_organization_id" not in authenticated_client.session


def test_switching_organization_changes_visible_expenses(tenant_client, project, user):
    first = ExpenseFactory(project=project)
    membership = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = ExpenseFactory(
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


def test_leaf_delete_preserves_expense_and_parent_restriction(tenant_client, stage):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    expense = ExpenseFactory(project=stage.project, stage=child)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    assert (
        tenant_client.delete(
            f"/api/v1/projects/{stage.project_id}/stages/{stage.pk}/"
        ).status_code
        == 409
    )
    expense.refresh_from_db()
    assert expense.stage_id == child.pk
    before = Expense.objects.values().get(pk=expense.pk)
    assert (
        tenant_client.delete(
            f"/api/v1/projects/{stage.project_id}/stages/{child.pk}/"
        ).status_code
        == 204
    )
    expense.refresh_from_db()
    assert expense.stage is None
    assert Expense.objects.values().get(pk=expense.pk) == {**before, "stage_id": None}
    assert not BudgetItem.objects.exists() and not StagePlan.objects.exists()
    assert Project.objects.filter(pk=expense.project_id).exists()


@pytest.mark.parametrize("status", ExpenseStatus.values)
def test_project_delete_protects_entire_graph_including_canceled(
    tenant_client, stage, status
):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    ExpenseFactory(project=stage.project, stage=child, status=status)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    models = [Project, ProjectStage, Expense, BudgetItem, StagePlan]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    response = tenant_client.delete(f"/api/v1/projects/{stage.project_id}/")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A obra possui registros financeiros e não pode ser excluída."
    }
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before


def test_project_without_expenses_still_cascades(tenant_client, stage):
    child = ProjectStageFactory(project=stage.project, parent=stage)
    BudgetItemFactory(stage=child)
    StagePlanFactory(stage=child)
    external = ExpenseFactory()
    assert (
        tenant_client.delete(f"/api/v1/projects/{stage.project_id}/").status_code == 204
    )
    assert not ProjectStage.objects.exists()
    assert not BudgetItem.objects.exists() and not StagePlan.objects.exists()
    external.refresh_from_db()
    assert Expense.objects.get() == external


def test_protected_project_from_another_tenant_stays_hidden(tenant_client):
    expense = ExpenseFactory()
    assert (
        tenant_client.delete(f"/api/v1/projects/{expense.project_id}/").status_code
        == 404
    )
    expense.refresh_from_db()


def test_project_delete_does_not_mask_unrelated_protection(
    tenant_client, project, monkeypatch
):
    def unexpected_protection(instance, *args, **kwargs):
        raise ProtectedError("Unrelated protection", {instance})

    monkeypatch.setattr(Project, "delete", unexpected_protection)
    with pytest.raises(ProtectedError, match="Unrelated protection"):
        tenant_client.delete(f"/api/v1/projects/{project.pk}/")
