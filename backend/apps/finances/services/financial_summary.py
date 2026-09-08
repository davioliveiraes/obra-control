from decimal import Decimal, localcontext

from django.db.models import Sum

from apps.projects.models import Project

from ..models import Expense, ExpenseStatus, Revenue, RevenueStatus

ZERO = Decimal("0.00")
# Totals can exceed the precision of one amount, including sums across BigAutoField IDs.
FINANCIAL_SUMMARY_DECIMAL_PRECISION = 48


def get_project_financial_summary(project: Project) -> dict:
    """Aggregate realized movements; the caller must authorize the Project first."""
    revenue_total = (
        Revenue.objects.filter(project=project, status=RevenueStatus.ACTIVE).aggregate(
            total=Sum("amount")
        )["total"]
        or ZERO
    )
    expense_total = (
        Expense.objects.filter(project=project, status=ExpenseStatus.ACTIVE).aggregate(
            total=Sum("amount")
        )["total"]
        or ZERO
    )

    # PostgreSQL SUM preserves the amounts' two decimal places. Keep subtraction
    # exact for large totals without changing the application's global context.
    with localcontext() as context:
        context.prec = FINANCIAL_SUMMARY_DECIMAL_PRECISION
        return {
            "project_id": project.pk,
            "revenue_total": revenue_total,
            "expense_total": expense_total,
            "realized_balance": revenue_total - expense_total,
        }
