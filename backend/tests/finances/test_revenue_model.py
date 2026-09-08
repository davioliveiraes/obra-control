from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.budgets.models import BudgetItem
from apps.customers.models import Customer
from apps.finances.models import Expense, Revenue, RevenueStatus
from apps.organizations.models import Membership
from apps.planning.models import StagePlan
from apps.projects.models import Project
from tests.factories.finances import RevenueFactory
from tests.factories.projects import ProjectFactory

pytestmark = pytest.mark.django_db


def test_revenue_defaults_decimal_required_context_and_timestamps():
    before = timezone.now()
    revenue = RevenueFactory()
    revenue.full_clean()
    revenue.refresh_from_db()
    assert revenue.project.revenues.get() == revenue
    assert revenue.status == RevenueStatus.ACTIVE and revenue.notes == ""
    assert isinstance(revenue.amount, Decimal) and revenue.amount == Decimal("100.00")
    assert revenue.revenue_date == date(2026, 9, 5)
    assert before <= revenue.created_at <= revenue.updated_at <= timezone.now()
    assert timezone.is_aware(revenue.created_at)
    assert {field.name for field in Revenue._meta.fields} == {
        "id",
        "project",
        "description",
        "amount",
        "revenue_date",
        "status",
        "notes",
        "created_at",
        "updated_at",
    }
    for model in [Customer, Membership, Expense, BudgetItem, StagePlan]:
        assert not model.objects.exists()


@pytest.mark.parametrize("field", ["project", "description", "amount", "revenue_date"])
def test_required_fields_in_validation_and_postgresql(field):
    revenue = RevenueFactory.build(project=ProjectFactory())
    setattr(revenue, field, None)
    with pytest.raises(ValidationError) as error:
        revenue.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        revenue.save()
    assert error.value.__cause__.diag.column_name == (
        "project_id" if field == "project" else field
    )


def test_description_required_but_not_unique():
    revenue = RevenueFactory()
    RevenueFactory(project=revenue.project, description=revenue.description)
    revenue.description = ""
    with pytest.raises(ValidationError) as error:
        revenue.full_clean()
    assert "description" in error.value.message_dict
    assert revenue.project.revenues.count() == 2


@pytest.mark.parametrize("amount", ["0", "0.00", "-0.01", "-100"])
def test_amount_positive_in_model_and_postgresql_create_and_update(amount):
    assert connection.vendor == "postgresql"
    revenue = RevenueFactory()
    invalid = RevenueFactory.build(project=revenue.project, amount=Decimal(amount))
    with pytest.raises(ValidationError):
        invalid.full_clean()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        invalid.save()
    assert (
        error.value.__cause__.diag.constraint_name == "finances_revenue_amount_positive"
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Revenue.objects.filter(pk=revenue.pk).update(amount=Decimal(amount))
    assert (
        error.value.__cause__.diag.constraint_name == "finances_revenue_amount_positive"
    )
    revenue.refresh_from_db()
    assert revenue.amount == Decimal("100.00")


def test_status_choices_reject_receivable_or_payment_states():
    revenue = RevenueFactory(status=RevenueStatus.CANCELED)
    revenue.full_clean()
    assert revenue.amount == Decimal("100.00")
    revenue.status = "paid"
    with pytest.raises(ValidationError) as error:
        revenue.full_clean()
    assert "status" in error.value.message_dict


@pytest.mark.parametrize("status", RevenueStatus.values)
def test_even_canceled_revenue_protects_project(status):
    revenue = RevenueFactory(status=status)
    with pytest.raises(ProtectedError):
        revenue.project.delete()
    assert Project.objects.filter(pk=revenue.project_id).exists()
    revenue.refresh_from_db()
    assert revenue.status == status and revenue.amount == Decimal("100.00")


def test_database_enforces_project_foreign_key():
    revenue = RevenueFactory()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Revenue.objects.filter(pk=revenue.pk).update(project_id=9223372036854775807)
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"


def test_project_without_financial_records_is_deletable():
    project = ProjectFactory()
    project_id = project.pk
    project.delete()
    assert not Project.objects.filter(pk=project_id).exists()
