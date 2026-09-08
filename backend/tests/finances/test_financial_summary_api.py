import re
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.budgets.models import BudgetItem
from apps.finances.models import Expense, ExpenseStatus, Revenue, RevenueStatus
from apps.organizations.models import MembershipRole
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory

pytestmark = pytest.mark.django_db


def url(project):
    return f"/api/v1/projects/{project.pk}/financial-summary/"


@pytest.mark.parametrize("role", MembershipRole.values)
def test_all_active_roles_can_read_without_csrf_and_receive_money_strings(
    tenant_client, membership, project, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    RevenueFactory(project=project, amount=Decimal("1000.00"))
    ExpenseFactory(project=project, amount=Decimal("1200.00"))
    tenant_client.credentials()  # The shared client enforces CSRF; safe reads need no token.
    response = tenant_client.get(url(project))
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert response.json() == {
        "project_id": project.pk,
        "revenue_total": "1000.00",
        "expense_total": "1200.00",
        "realized_balance": "-200.00",
    }
    for field in ["revenue_total", "expense_total", "realized_balance"]:
        value = response.json()[field]
        assert isinstance(value, str) and re.fullmatch(r"-?\d+\.\d{2}", value)
    assert tenant_client.head(url(project)).status_code == 200
    assert tenant_client.options(url(project)).status_code == 200


def test_empty_project_returns_all_three_zero_strings(tenant_client, project):
    response = tenant_client.get(url(project))
    assert response.status_code == 200
    assert response.json() == {
        "project_id": project.pk,
        "revenue_total": "0.00",
        "expense_total": "0.00",
        "realized_balance": "0.00",
    }


@pytest.mark.parametrize("superuser", [False, True])
def test_other_tenant_and_missing_project_return_identical_404(
    tenant_client, user, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    revenue = RevenueFactory()
    ExpenseFactory(project=revenue.project, amount=Decimal("99000.00"))
    response = tenant_client.get(url(revenue.project))
    missing = tenant_client.get(
        "/api/v1/projects/9223372036854775807/financial-summary/"
    )
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    assert set(response.json()) == {"detail"}


@pytest.mark.parametrize("superuser", [False, True])
def test_anonymous_and_missing_context_cannot_read(
    authenticated_client, user, project, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    for client in [APIClient(enforce_csrf_checks=True), authenticated_client]:
        assert client.get(url(project)).status_code == 403


def test_no_write_methods_or_financial_mutations(tenant_client, project):
    RevenueFactory(project=project)
    ExpenseFactory(project=project)
    models = [Project, Revenue, Expense]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    for method in ["post", "put", "patch", "delete"]:
        assert (
            getattr(tenant_client, method)(
                url(project), {"realized_balance": "99999.99"}, format="json"
            ).status_code
            == 405
        )
    assert tenant_client.get(url(project)).status_code == 200
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before


def test_revocation_denies_the_next_request(tenant_client, membership, project):
    assert tenant_client.get(url(project)).status_code == 200
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert tenant_client.get(url(project)).status_code == 403
    assert "current_organization_id" not in tenant_client.session


def test_switching_organization_changes_access_without_storing_summary_in_session(
    tenant_client, project, user
):
    RevenueFactory(project=project, amount=Decimal("100.00"))
    ExpenseFactory(project=project, amount=Decimal("70.00"))
    other = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    other_project = ProjectFactory(organization=other.organization)
    RevenueFactory(project=other_project, amount=Decimal("200.00"))
    ExpenseFactory(project=other_project, amount=Decimal("80.00"))
    session_before = dict(tenant_client.session)
    assert tenant_client.get(url(project)).json()["realized_balance"] == "30.00"
    assert dict(tenant_client.session) == session_before
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
    assert tenant_client.get(url(other_project)).json() == {
        "project_id": other_project.pk,
        "revenue_total": "200.00",
        "expense_total": "80.00",
        "realized_balance": "120.00",
    }


def test_active_totals_are_recomputed_without_date_filters_or_cache(
    tenant_client, project
):
    revenue = RevenueFactory(project=project, amount=Decimal("1000.00"))
    expense = ExpenseFactory(project=project, amount=Decimal("700.00"))
    RevenueFactory(
        project=project, status=RevenueStatus.CANCELED, amount=Decimal("9000.00")
    )
    ExpenseFactory(
        project=project, status=ExpenseStatus.CANCELED, amount=Decimal("5000.00")
    )
    params = {
        "date_from": "2099-01-01",
        "date_to": "2099-02-01",
        "page": 2,
        "project_id": 9223372036854775807,
    }
    assert tenant_client.get(url(project), params).json() == {
        "project_id": project.pk,
        "revenue_total": "1000.00",
        "expense_total": "700.00",
        "realized_balance": "300.00",
    }
    revenue.status = RevenueStatus.CANCELED
    revenue.save(update_fields=["status"])
    assert (
        tenant_client.get(url(project), params).json()["realized_balance"] == "-700.00"
    )
    expense.status = ExpenseStatus.CANCELED
    expense.save(update_fields=["status"])
    assert tenant_client.get(url(project), params).json() == {
        "project_id": project.pk,
        "revenue_total": "0.00",
        "expense_total": "0.00",
        "realized_balance": "0.00",
    }


def test_cost_summary_and_sources_remain_unchanged(tenant_client, stage):
    BudgetItemFactory(stage=stage, unit_price=Decimal("1000.00"))
    StagePlanFactory(stage=stage)
    RevenueFactory(project=stage.project, amount=Decimal("1500.00"))
    ExpenseFactory(project=stage.project, stage=stage, amount=Decimal("600.00"))
    ExpenseFactory(project=stage.project, amount=Decimal("100.00"))
    cost_url = f"/api/v1/projects/{stage.project_id}/cost-summary/"
    cost_before = tenant_client.get(cost_url).json()
    assert cost_before["budget_total"] == "1000.00"
    assert cost_before["actual_total"] == "700.00"
    assert cost_before["variance_amount"] == "300.00"
    models = [Project, ProjectStage, BudgetItem, StagePlan, Revenue, Expense]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    assert tenant_client.get(url(stage.project)).json() == {
        "project_id": stage.project_id,
        "revenue_total": "1500.00",
        "expense_total": "700.00",
        "realized_balance": "800.00",
    }
    assert tenant_client.get(cost_url).json() == cost_before
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before
