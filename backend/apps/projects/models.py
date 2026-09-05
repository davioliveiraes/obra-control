from django.core.exceptions import ValidationError
from django.db import models

from apps.customers.models import Customer


class ProjectStatus(models.TextChoices):
    PLANNING = "planning", "Planning"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class Project(models.Model):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="projects"
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=ProjectStatus.choices, default=ProjectStatus.PLANNING
    )
    description = models.TextField(blank=True)
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(planned_start_date__isnull=True)
                    | models.Q(planned_end_date__isnull=True)
                    | models.Q(planned_end_date__gte=models.F("planned_start_date"))
                ),
                name="projects_project_planned_dates_order",
                violation_error_message="A data final não pode ser anterior à inicial.",
            ),
        ]

    def clean(self):
        super().clean()
        # Explicit model/form validation; HTTP resolution is separately tenant-scoped.
        if (
            self.customer_id is not None
            and self.organization_id is not None
            and Customer.objects.using(self._state.db)
            .filter(pk=self.customer_id)
            .exclude(organization_id=self.organization_id)
            .exists()
        ):
            raise ValidationError(
                {"customer": "O cliente deve pertencer à mesma organização da obra."}
            )
