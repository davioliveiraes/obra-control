from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class BudgetItem(models.Model):
    stage = models.ForeignKey(
        "projects.ProjectStage", on_delete=models.CASCADE, related_name="budget_items"
    )
    description = models.CharField(max_length=255)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="budgets_budgetitem_quantity_positive",
                violation_error_message="A quantidade deve ser maior que zero.",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="budgets_budgetitem_unit_price_nonnegative",
                violation_error_message="O preço unitário não pode ser negativo.",
            ),
        ]

    @property
    def total(self):
        return self.quantity * self.unit_price
