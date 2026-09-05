from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.projects.models import Project, ProjectStatus
from tests.factories.customers import CustomerFactory
from tests.factories.organizations import OrganizationFactory
from tests.factories.projects import ProjectFactory

pytestmark = pytest.mark.django_db


def test_project_defaults_and_timestamps():
    before = timezone.now()
    project = ProjectFactory()
    project.refresh_from_db()
    assert project.organization.projects.get() == project
    assert project.customer is None
    assert project.status == ProjectStatus.PLANNING
    assert project.description == ""
    assert project.planned_start_date is project.planned_end_date is None
    assert before <= project.created_at <= project.updated_at <= timezone.now()
    assert timezone.is_aware(project.created_at)
    assert not project.organization.customers.exists()
    assert not project.organization.memberships.exists()


def test_database_requires_organization():
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Project.objects.create(name="Obra sem organização")
    assert error.value.__cause__.diag.column_name == "organization_id"


def test_database_enforces_organization_fk():
    organization = OrganizationFactory()
    missing_id = organization.pk
    organization.delete()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Project.objects.create(name="Obra", organization_id=missing_id)
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"


@pytest.mark.parametrize("status", ProjectStatus.values)
def test_status_choices_can_be_validated_and_persisted(status):
    project = ProjectFactory.build(organization=OrganizationFactory(), status=status)
    project.full_clean()
    project.save()
    project.refresh_from_db()
    assert project.status == status


@pytest.mark.parametrize(
    "field,value", [("name", ""), ("name", None), ("status", "bad")]
)
def test_model_validation_rejects_invalid_fields(field, value):
    project = ProjectFactory.build(organization=OrganizationFactory(), **{field: value})
    with pytest.raises(ValidationError) as error:
        project.full_clean()
    assert field in error.value.message_dict


def test_duplicate_names_are_allowed_within_and_between_tenants():
    first = ProjectFactory(name="Obra")
    second = ProjectFactory(organization=first.organization, name=first.name)
    third = ProjectFactory(name=first.name)
    assert first.organization_id != third.organization_id
    assert len({first.pk, second.pk, third.pk}) == 3
    assert Project.objects.filter(name=first.name).count() == 3


def test_same_tenant_customer_passes_model_validation_and_set_null_preserves_project():
    customer = CustomerFactory()
    project = ProjectFactory(organization=customer.organization, customer=customer)
    project.full_clean()
    assert customer.projects.get() == project
    customer.delete()
    project.refresh_from_db()
    assert project.customer_id is None
    assert project.organization_id is not None
    assert Project.objects.filter(pk=project.pk).exists()


def test_model_clean_rejects_customer_from_another_organization():
    project = ProjectFactory.build(
        organization=OrganizationFactory(), customer=CustomerFactory()
    )
    with pytest.raises(ValidationError) as error:
        project.full_clean()
    assert "customer" in error.value.message_dict


@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        (date(2026, 10, 1), None),
        (None, date(2026, 10, 1)),
        (date(2026, 10, 1), date(2026, 10, 1)),
        (date(2026, 10, 1), date(2026, 10, 10)),
    ],
)
def test_database_accepts_optional_and_ordered_dates(start, end):
    project = ProjectFactory(planned_start_date=start, planned_end_date=end)
    project.full_clean()
    project.refresh_from_db()
    assert project.planned_start_date == start
    assert project.planned_end_date == end


@pytest.mark.parametrize("operation", ["create", "update"])
def test_database_rejects_reversed_dates_even_without_model_validation(operation):
    organization = OrganizationFactory()
    project = ProjectFactory(organization=organization)
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        dates = {
            "planned_start_date": date(2026, 10, 10),
            "planned_end_date": date(2026, 10, 1),
        }
        if operation == "create":
            Project.objects.create(organization=organization, name="Inválida", **dates)
        else:
            Project.objects.filter(pk=project.pk).update(**dates)
    assert (
        error.value.__cause__.diag.constraint_name
        == "projects_project_planned_dates_order"
    )
    project.refresh_from_db()
    assert project.planned_start_date is project.planned_end_date is None


def test_organization_cascade_does_not_delete_other_tenant_projects():
    owned = ProjectFactory()
    other = ProjectFactory()
    owned.organization.delete()
    assert not Project.objects.filter(pk=owned.pk).exists()
    assert Project.objects.filter(pk=other.pk).exists()
