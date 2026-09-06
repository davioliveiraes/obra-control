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


class ProjectStage(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="stages"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(parent__isnull=True)
                | ~models.Q(id=models.F("parent_id")),
                name="projects_projectstage_not_self_parent",
            ),
        ]

    def clean(self):
        super().clean()
        if self.parent_id is None:
            return
        if self.pk is not None and self.parent_id == self.pk:
            raise ValidationError(
                {"parent": "A etapa não pode ser seu próprio parent."}
            )
        visited = {self.pk} if self.pk is not None else set()
        ancestor_id = self.parent_id
        while ancestor_id is not None:
            if ancestor_id in visited:
                raise ValidationError(
                    {"parent": "O vínculo informado formaria um ciclo."}
                )
            visited.add(ancestor_id)
            ancestor = (
                ProjectStage.objects.using(self._state.db)
                .filter(pk=ancestor_id, project_id=self.project_id)
                .values("parent_id")
                .first()
            )
            if ancestor is None:
                raise ValidationError(
                    {"parent": "A etapa pai deve pertencer ao mesmo Project."}
                )
            ancestor_id = ancestor["parent_id"]
