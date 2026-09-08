from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.projects.models import ProjectStage


class ExpenseStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELED = "canceled", "Canceled"


class Expense(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="expenses"
    )
    stage = models.ForeignKey(
        ProjectStage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    expense_date = models.DateField()
    status = models.CharField(
        max_length=8, choices=ExpenseStatus.choices, default=ExpenseStatus.ACTIVE
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="finances_expense_amount_positive",
                violation_error_message="O valor da despesa deve ser maior que zero.",
            ),
        ]

    def clean(self):
        super().clean()
        # Explicit model/form validation; the API separately scopes stage resolution.
        if (
            self.stage_id is not None
            and self.project_id is not None
            and ProjectStage.objects.using(self._state.db)
            .filter(pk=self.stage_id)
            .exclude(project_id=self.project_id)
            .exists()
        ):
            raise ValidationError(
                {"stage": "A etapa deve pertencer à mesma obra da despesa."}
            )


class RevenueStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELED = "canceled", "Canceled"


class Revenue(models.Model):
    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="revenues"
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    revenue_date = models.DateField()
    status = models.CharField(
        max_length=8, choices=RevenueStatus.choices, default=RevenueStatus.ACTIVE
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="finances_revenue_amount_positive",
                violation_error_message="O valor da receita deve ser maior que zero.",
            ),
        ]
