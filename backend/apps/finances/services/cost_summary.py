from decimal import ROUND_HALF_UP, Decimal, localcontext

from apps.budgets.models import BudgetItem
from apps.projects.models import Project, ProjectStage

from ..models import Expense, ExpenseStatus

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
# Aggregates need more precision than individual fields/products. This also
# accommodates sums across the BigAutoField range, without changing global context.
SUMMARY_DECIMAL_PRECISION = 48


def get_project_cost_summary(project: Project) -> dict:
    """Read direct costs in three queries; caller must authorize the Project first."""
    stage_ids = list(
        ProjectStage.objects.filter(project=project)
        .order_by("position", "id")
        .values_list("id", flat=True)
    )
    items = BudgetItem.objects.filter(stage__project=project).values_list(
        "stage_id", "quantity", "unit_price"
    )
    expenses = Expense.objects.filter(
        project=project, status=ExpenseStatus.ACTIVE
    ).values_list("stage_id", "amount")

    with localcontext() as context:
        context.prec = SUMMARY_DECIMAL_PRECISION
        budget_total = actual_total = unallocated_actual_total = ZERO
        stage_budgets = {}
        stage_actuals = {}
        for stage_id, quantity, unit_price in items:
            # Match BudgetItem's API: round EACH item, not just the final sum.
            amount = (quantity * unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
            budget_total += amount
            stage_budgets[stage_id] = stage_budgets.get(stage_id, ZERO) + amount

        for stage_id, amount in expenses:
            actual_total += amount
            if stage_id is None:
                unallocated_actual_total += amount
            else:
                stage_actuals[stage_id] = stage_actuals.get(stage_id, ZERO) + amount

        stages = []
        for stage_id in stage_ids:
            budget = stage_budgets.get(stage_id, ZERO)
            actual = stage_actuals.get(stage_id, ZERO)
            stages.append(
                {
                    "stage_id": stage_id,
                    "budget_total": budget,
                    "actual_total": actual,
                    "variance_amount": budget - actual,
                }
            )
        return {
            "project_id": project.pk,
            "budget_total": budget_total,
            "actual_total": actual_total,
            "variance_amount": budget_total - actual_total,
            "unallocated_actual_total": unallocated_actual_total,
            "stages": stages,
        }
