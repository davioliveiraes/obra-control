import re
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.finances.models import Expense, ExpenseStatus
from apps.organizations.models import MembershipRole
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db


def url(project):
    return f"/api/v1/projects/{project.pk}/cost-summary/"


@pytest.mark.parametrize("role", MembershipRole.values)
def test_all_active_roles_can_read_without_csrf_and_receive_decimal_strings(
    tenant_client, membership, stage, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    BudgetItemFactory(stage=stage, unit_price=Decimal("1000.00"))
    ExpenseFactory(project=stage.project, stage=stage, amount=Decimal("100.00"))
    ExpenseFactory(project=stage.project, amount=Decimal("50.00"))
    ExpenseFactory(
        project=stage.project,
        stage=stage,
        status=ExpenseStatus.CANCELED,
        amount=Decimal("500.00"),
    )
    tenant_client.credentials()  # GET must work without X-CSRFToken.
    response = tenant_client.get(url(stage.project))
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    data = response.json()
    assert data == {
        "project_id": stage.project_id,
        "budget_total": "1000.00",
        "actual_total": "150.00",
        "variance_amount": "850.00",
        "unallocated_actual_total": "50.00",
        "stages": [
            {
                "stage_id": stage.pk,
                "budget_total": "1000.00",
                "actual_total": "100.00",
                "variance_amount": "900.00",
            }
        ],
    }
    for row in [data, *data["stages"]]:
        for name in ["budget_total", "actual_total", "variance_amount"]:
            assert isinstance(row[name], str) and re.fullmatch(
                r"-?\d+\.\d{2}", row[name]
            )
    assert tenant_client.head(url(stage.project)).status_code == 200
    assert tenant_client.options(url(stage.project)).status_code == 200


def test_empty_project_serializes_zero_not_null(tenant_client, project):
    response = tenant_client.get(url(project))
    assert response.status_code == 200
    assert response.json() == {
        "project_id": project.pk,
        "budget_total": "0.00",
        "actual_total": "0.00",
        "variance_amount": "0.00",
        "unallocated_actual_total": "0.00",
        "stages": [],
    }


@pytest.mark.parametrize("superuser", [False, True])
def test_foreign_project_and_nonexistent_project_have_same_404(
    tenant_client, user, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    item = BudgetItemFactory()
    ExpenseFactory(project=item.stage.project, amount=Decimal("9999.99"))
    response = tenant_client.get(url(item.stage.project))
    missing = tenant_client.get("/api/v1/projects/9223372036854775807/cost-summary/")
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    assert (
        "budget_total" not in response.json() and "actual_total" not in response.json()
    )


@pytest.mark.parametrize("superuser", [False, True])
def test_anonymous_and_missing_organization_cannot_read(
    authenticated_client, user, project, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        assert client.get(url(project)).status_code == 403


def test_no_write_methods_and_get_never_changes_financial_sources(tenant_client, stage):
    BudgetItemFactory(stage=stage)
    ExpenseFactory(project=stage.project, stage=stage)
    before = {
        model: list(model.objects.order_by("pk").values())
        for model in [BudgetItem, Expense]
    }
    for method in ["post", "put", "patch", "delete"]:
        assert (
            getattr(tenant_client, method)(
                url(stage.project), {"actual_total": "9999.99"}, format="json"
            ).status_code
            == 405
        )
    assert tenant_client.get(url(stage.project)).status_code == 200
    assert {
        model: list(model.objects.order_by("pk").values())
        for model in [BudgetItem, Expense]
    } == before


def test_revoked_membership_invalidates_summary_access(
    tenant_client, membership, project
):
    assert tenant_client.get(url(project)).status_code == 200
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert tenant_client.get(url(project)).status_code == 403
    assert "current_organization_id" not in tenant_client.session


def test_switching_tenant_changes_summary_and_never_reuses_previous_data(
    tenant_client, project, user
):
    ExpenseFactory(project=project, amount=Decimal("10.00"))
    other = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    other_project = ProjectFactory(organization=other.organization)
    ExpenseFactory(project=other_project, amount=Decimal("20.00"))
    assert tenant_client.get(url(project)).json()["actual_total"] == "10.00"
    assert tenant_client.get(url(other_project)).status_code == 404
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": other.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(url(project)).status_code == 404
    assert tenant_client.get(url(other_project)).json()["actual_total"] == "20.00"


def test_current_sources_are_recomputed_without_filters_or_pagination(
    tenant_client, project
):
    stages = ProjectStageFactory.create_batch(26, project=project)
    expense = ExpenseFactory(project=project, stage=stages[0], amount=Decimal("50.00"))
    item = BudgetItemFactory(stage=stages[0])
    params = {
        "page": 2,
        "date_from": "2099-01-01",
        "stage": stages[-1].pk,
        "project_id": 9223372036854775807,
    }
    data = tenant_client.get(url(project), params).json()
    assert len(data["stages"]) == 26 and data["actual_total"] == "50.00"
    expense.status = ExpenseStatus.CANCELED
    expense.save(update_fields=["status"])
    item.unit_price = Decimal("20.00")
    item.save(update_fields=["unit_price"])
    data = tenant_client.get(url(project), params).json()
    assert data["budget_total"] == "20.00" and data["actual_total"] == "0.00"
    assert data["variance_amount"] == "20.00"
