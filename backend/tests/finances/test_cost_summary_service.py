from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.budgets.api.serializers import BudgetItemSerializer
from apps.budgets.models import BudgetItem
from apps.finances.api.cost_summary_serializers import CostSummarySerializer
from apps.finances.models import Expense, ExpenseStatus
from apps.finances.services.cost_summary import get_project_cost_summary
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.finances import ExpenseFactory
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
ZERO = Decimal("0.00")


def test_empty_project_has_decimal_zeros_without_stages():
    project = ProjectFactory()
    assert get_project_cost_summary(project) == {
        "project_id": project.pk,
        "budget_total": ZERO,
        "actual_total": ZERO,
        "variance_amount": ZERO,
        "unallocated_actual_total": ZERO,
        "stages": [],
    }


@pytest.mark.parametrize(
    "budget,actual,variance",
    [
        ("1000.00", "700.00", "300.00"),
        ("1000.00", "1200.00", "-200.00"),
        ("1000.00", "1000.00", "0.00"),
        ("1000.00", "0.00", "1000.00"),
        ("0.00", "500.00", "-500.00"),
    ],
)
def test_totals_and_signed_variance_from_independent_sources(budget, actual, variance):
    stage = ProjectStageFactory()
    if Decimal(budget):
        BudgetItemFactory(stage=stage, unit_price=Decimal(budget))
    if Decimal(actual):
        ExpenseFactory(project=stage.project, stage=stage, amount=Decimal(actual))
    result = get_project_cost_summary(stage.project)
    expected = {
        "budget_total": Decimal(budget),
        "actual_total": Decimal(actual),
        "variance_amount": Decimal(variance),
    }
    for field, value in expected.items():
        assert result[field] == value and isinstance(result[field], Decimal)
        assert result[field].as_tuple().exponent == -2
    assert result["unallocated_actual_total"] == ZERO
    assert result["stages"] == [{"stage_id": stage.pk, **expected}]


def test_canceled_expenses_excluded_and_general_expenses_only_in_project():
    stage = ProjectStageFactory(position=3)
    empty = ProjectStageFactory(project=stage.project, position=0)
    ExpenseFactory(project=stage.project, stage=stage, amount=Decimal("100.00"))
    ExpenseFactory(
        project=stage.project,
        stage=stage,
        amount=Decimal("500.00"),
        status=ExpenseStatus.CANCELED,
    )
    ExpenseFactory(project=stage.project, amount=Decimal("50.00"))
    ExpenseFactory(
        project=stage.project, amount=Decimal("600.00"), status=ExpenseStatus.CANCELED
    )
    result = get_project_cost_summary(stage.project)
    assert result["actual_total"] == Decimal("150.00")
    assert result["unallocated_actual_total"] == Decimal("50.00")
    assert result["variance_amount"] == Decimal("-150.00")
    assert result["stages"] == [
        {
            "stage_id": empty.pk,
            "budget_total": ZERO,
            "actual_total": ZERO,
            "variance_amount": ZERO,
        },
        {
            "stage_id": stage.pk,
            "budget_total": ZERO,
            "actual_total": Decimal("100.00"),
            "variance_amount": Decimal("-100.00"),
        },
    ]


def test_child_values_are_direct_and_never_rolled_up_to_parent():
    parent = ProjectStageFactory()
    child = ProjectStageFactory(project=parent.project, parent=parent)
    BudgetItemFactory(stage=child, unit_price=Decimal("100.00"))
    ExpenseFactory(project=parent.project, stage=child, amount=Decimal("30.00"))
    result = get_project_cost_summary(parent.project)
    assert result["budget_total"] == Decimal("100.00")
    assert result["actual_total"] == Decimal("30.00")
    assert result["stages"] == [
        {
            "stage_id": parent.pk,
            "budget_total": ZERO,
            "actual_total": ZERO,
            "variance_amount": ZERO,
        },
        {
            "stage_id": child.pk,
            "budget_total": Decimal("100.00"),
            "actual_total": Decimal("30.00"),
            "variance_amount": Decimal("70.00"),
        },
    ]


@pytest.mark.parametrize(
    "quantity,price,total",
    [
        ("0.3333", "3.00", "2.00"),
        ("0.0050", "1.00", "0.02"),
        ("1.0050", "1.00", "2.02"),
    ],
)
def test_rounds_each_item_like_budget_api_before_summing(quantity, price, total):
    stage = ProjectStageFactory()
    items = BudgetItemFactory.create_batch(
        2, stage=stage, quantity=Decimal(quantity), unit_price=Decimal(price)
    )
    visual_total = sum(
        (Decimal(BudgetItemSerializer(item).data["total"]) for item in items), ZERO
    )
    result = get_project_cost_summary(stage.project)
    assert result["budget_total"] == visual_total == Decimal(total)
    assert result["stages"][0]["budget_total"] == Decimal(total)
    assert CostSummarySerializer(result).data["budget_total"] == total


def test_summary_can_exceed_individual_item_digits_without_losing_cents():
    stage = ProjectStageFactory()
    BudgetItemFactory.create_batch(
        2,
        stage=stage,
        quantity=Decimal("9999999999.9999"),
        unit_price=Decimal("999999999999.99"),
    )
    ExpenseFactory(project=stage.project, amount=Decimal("0.01"))
    result = get_project_cost_summary(stage.project)
    assert result["budget_total"] == Decimal("19999999999999600000000.00")
    assert result["variance_amount"] == Decimal("19999999999999599999999.99")
    data = CostSummarySerializer(result).data
    assert data["budget_total"] == "19999999999999600000000.00"
    assert data["variance_amount"] == "19999999999999599999999.99"


def test_service_reads_only_given_project_and_never_mutates_sources_or_planning():
    project = ProjectFactory()
    stage = ProjectStageFactory(project=project)
    BudgetItemFactory(stage=stage)
    ExpenseFactory(project=project, stage=stage)
    StagePlanFactory(stage=stage)
    for other in [ProjectFactory(organization=project.organization), ProjectFactory()]:
        other_stage = ProjectStageFactory(project=other)
        BudgetItemFactory(stage=other_stage, unit_price=Decimal("10000.00"))
        ExpenseFactory(project=other, amount=Decimal("20000.00"))
    models = [Project, ProjectStage, StagePlan, BudgetItem, Expense]
    before = {model: list(model.objects.order_by("pk").values()) for model in models}
    result = get_project_cost_summary(project)
    assert result["budget_total"] == Decimal("10.00")
    assert result["actual_total"] == Decimal("100.00")
    assert [row["stage_id"] for row in result["stages"]] == [stage.pk]
    assert {
        model: list(model.objects.order_by("pk").values()) for model in models
    } == before


@pytest.mark.parametrize("stage_count", [0, 1, 30])
def test_service_uses_three_selects_independent_of_stage_count(
    stage_count, django_assert_num_queries
):
    project = ProjectFactory()
    for stage in ProjectStageFactory.create_batch(stage_count, project=project):
        BudgetItemFactory.create_batch(2, stage=stage)
        ExpenseFactory.create_batch(3, project=project, stage=stage)
    # Stable service boundary: one SELECT for stages, items, and active expenses.
    # Authentication and the scoped Project lookup belong to the HTTP layer.
    with django_assert_num_queries(3) as captured:
        result = get_project_cost_summary(project)
    assert all(
        query["sql"].lstrip().upper().startswith("SELECT")
        for query in captured.captured_queries
    )
    assert result["budget_total"] == Decimal("20.00") * stage_count
    assert result["actual_total"] == Decimal("300.00") * stage_count
    assert len(result["stages"]) == stage_count


def test_models_have_no_pending_migration_changes():
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)
