from decimal import Decimal, localcontext

import pytest
from django.db import connection

from apps.finances.api.financial_summary_serializers import (
    ProjectFinancialSummarySerializer,
)
from apps.finances.models import ExpenseStatus, RevenueStatus
from apps.finances.services.financial_summary import get_project_financial_summary
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory, RevenueFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
ZERO = Decimal("0.00")


@pytest.mark.parametrize(
    "revenue,expense,balance",
    [
        ("0.00", "0.00", "0.00"),
        ("800.00", "0.00", "800.00"),
        ("0.00", "800.00", "-800.00"),
        ("1500.00", "1000.00", "500.00"),
        ("1000.00", "1500.00", "-500.00"),
        ("1000.00", "1000.00", "0.00"),
    ],
)
def test_empty_one_sided_and_signed_balances_preserve_decimal(
    revenue, expense, balance
):
    project = ProjectFactory()
    if Decimal(revenue):
        RevenueFactory(project=project, amount=Decimal(revenue))
    if Decimal(expense):
        ExpenseFactory(project=project, amount=Decimal(expense))
    result = get_project_financial_summary(project)
    assert result == {
        "project_id": project.pk,
        "revenue_total": Decimal(revenue),
        "expense_total": Decimal(expense),
        "realized_balance": Decimal(balance),
    }
    for field in ["revenue_total", "expense_total", "realized_balance"]:
        assert isinstance(result[field], Decimal)
        assert result[field].as_tuple().exponent == -2


def test_canceled_movements_never_contribute_to_active_totals():
    project = ProjectFactory()
    RevenueFactory(project=project, amount=Decimal("1000.00"))
    RevenueFactory(
        project=project, amount=Decimal("9000.00"), status=RevenueStatus.CANCELED
    )
    ExpenseFactory(project=project, amount=Decimal("700.00"))
    ExpenseFactory(
        project=project, amount=Decimal("5000.00"), status=ExpenseStatus.CANCELED
    )
    assert get_project_financial_summary(project) == {
        "project_id": project.pk,
        "revenue_total": Decimal("1000.00"),
        "expense_total": Decimal("700.00"),
        "realized_balance": Decimal("300.00"),
    }


def test_only_canceled_records_return_zero_not_null():
    project = ProjectFactory()
    RevenueFactory(project=project, status=RevenueStatus.CANCELED)
    ExpenseFactory(project=project, status=ExpenseStatus.CANCELED)
    assert get_project_financial_summary(project) == {
        "project_id": project.pk,
        "revenue_total": ZERO,
        "expense_total": ZERO,
        "realized_balance": ZERO,
    }


def test_expenses_with_or_without_stage_both_contribute():
    stage = ProjectStageFactory()
    ExpenseFactory(project=stage.project, stage=stage, amount=Decimal("100.00"))
    ExpenseFactory(project=stage.project, amount=Decimal("50.00"))
    ExpenseFactory(project=stage.project, stage=stage, status=ExpenseStatus.CANCELED)
    result = get_project_financial_summary(stage.project)
    assert result["expense_total"] == Decimal("150.00")
    assert result["realized_balance"] == Decimal("-150.00")


def test_totals_exceed_individual_field_precision_without_losing_cents():
    project = ProjectFactory()
    RevenueFactory.create_batch(2, project=project, amount=Decimal("999999999999.99"))
    RevenueFactory(project=project, amount=Decimal("0.10"))
    RevenueFactory(project=project, amount=Decimal("0.20"))
    ExpenseFactory(project=project, amount=Decimal("0.01"))
    # The service does not inherit a caller's reduced precision for subtraction.
    with localcontext() as context:
        context.prec = 6
        result = get_project_financial_summary(project)
        assert context.prec == 6
    assert result["revenue_total"] == Decimal("2000000000000.28")
    assert result["realized_balance"] == Decimal("2000000000000.27")
    assert ProjectFinancialSummarySerializer(result).data == {
        "project_id": project.pk,
        "revenue_total": "2000000000000.28",
        "expense_total": "0.01",
        "realized_balance": "2000000000000.27",
    }


def test_aggregates_only_the_supplied_project_even_within_same_tenant():
    project = ProjectFactory()
    RevenueFactory(project=project, amount=Decimal("100.00"))
    ExpenseFactory(project=project, amount=Decimal("70.00"))
    for other in [ProjectFactory(organization=project.organization), ProjectFactory()]:
        RevenueFactory(project=other, amount=Decimal("90000.00"))
        ExpenseFactory(project=other, amount=Decimal("80000.00"))
    assert get_project_financial_summary(project) == {
        "project_id": project.pk,
        "revenue_total": Decimal("100.00"),
        "expense_total": Decimal("70.00"),
        "realized_balance": Decimal("30.00"),
    }


@pytest.mark.parametrize("record_count", [0, 10, 100])
def test_two_sql_sums_independent_of_record_count_without_eap_budget_or_planning(
    record_count, django_assert_num_queries
):
    assert connection.vendor == "postgresql"
    project = ProjectFactory()
    stage = ProjectStageFactory(project=project)
    BudgetItemFactory(stage=stage, unit_price=Decimal("9999.99"))
    StagePlanFactory(stage=stage)
    RevenueFactory.create_batch(record_count, project=project, amount=Decimal("10.00"))
    ExpenseFactory.create_batch(record_count, project=project, amount=Decimal("7.00"))
    # Only the service is measured: auth and the view's scoped Project lookup are separate.
    with django_assert_num_queries(2) as captured:
        result = get_project_financial_summary(project)
    assert result["revenue_total"] == Decimal("10.00") * record_count
    assert result["expense_total"] == Decimal("7.00") * record_count
    assert result["realized_balance"] == Decimal("3.00") * record_count
    for query, table in zip(
        captured.captured_queries, ["finances_revenue", "finances_expense"], strict=True
    ):
        sql = query["sql"].upper()
        assert sql.lstrip().startswith("SELECT") and "SUM(" in sql
        assert table.upper() in sql
        assert not any(name in sql for name in ["PROJECTS_", "BUDGETS_", "PLANNING_"])
