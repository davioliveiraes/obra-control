from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.budgets.models import BudgetItem
from apps.finances.models import Expense, ExpenseStatus
from apps.organizations.models import Membership
from apps.planning.models import StagePlan
from apps.projects.models import Project, ProjectStage
from tests.factories.finances import ExpenseFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_expense_defaults_required_context_and_timestamps():
    before = timezone.now()
    expense = ExpenseFactory()
    expense.full_clean()
    expense.refresh_from_db()
    assert expense.project.expenses.get() == expense
    assert expense.stage is None and expense.notes == ""
    assert expense.status == ExpenseStatus.ACTIVE
    assert isinstance(expense.amount, Decimal)
    assert expense.amount == Decimal("100.00")
    assert before <= expense.created_at <= expense.updated_at <= timezone.now()
    assert timezone.is_aware(expense.created_at)
    assert expense.expense_date == date(2026, 9, 6)
    assert {f.name for f in Expense._meta.fields} == {
        "id",
        "project",
        "stage",
        "description",
        "amount",
        "expense_date",
        "status",
        "notes",
        "created_at",
        "updated_at",
    }
    assert not Membership.objects.exists()
    assert not BudgetItem.objects.exists() and not StagePlan.objects.exists()


@pytest.mark.parametrize("field", ["project", "description", "amount", "expense_date"])
def test_required_fields_in_validation_and_postgresql(field):
    expense = ExpenseFactory.build(project=ProjectFactory())
    setattr(expense, field, None)
    with pytest.raises(ValidationError) as error:
        expense.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        expense.save()
    assert error.value.__cause__.diag.column_name == (
        "project_id" if field == "project" else field
    )


def test_blank_description_invalid_but_repeated_descriptions_allowed():
    expense = ExpenseFactory()
    ExpenseFactory(project=expense.project, description=expense.description)
    expense.description = ""
    with pytest.raises(ValidationError) as error:
        expense.full_clean()
    assert "description" in error.value.message_dict
    assert expense.project.expenses.count() == 2


@pytest.mark.parametrize("amount", ["0", "0.00", "-0.01", "-100"])
def test_amount_positive_validation_and_database_constraint(amount):
    expense = ExpenseFactory()
    invalid = ExpenseFactory.build(project=expense.project, amount=Decimal(amount))
    with pytest.raises(ValidationError):
        invalid.full_clean()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        invalid.save()
    assert (
        error.value.__cause__.diag.constraint_name == "finances_expense_amount_positive"
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Expense.objects.filter(pk=expense.pk).update(amount=Decimal(amount))
    assert (
        error.value.__cause__.diag.constraint_name == "finances_expense_amount_positive"
    )
    expense.refresh_from_db()
    assert expense.amount == Decimal("100.00")


def test_status_choices_do_not_imply_payment_state():
    expense = ExpenseFactory(status=ExpenseStatus.CANCELED)
    expense.full_clean()
    assert expense.amount == Decimal("100.00")
    expense.status = "paid"
    with pytest.raises(ValidationError) as error:
        expense.full_clean()
    assert "status" in error.value.message_dict


@pytest.mark.parametrize("same_tenant", [False, True])
def test_model_validation_rejects_stage_from_another_project(same_tenant):
    expense = ExpenseFactory()
    project = (
        ProjectFactory(organization=expense.project.organization)
        if same_tenant
        else ProjectFactory()
    )
    expense.stage = ProjectStageFactory(project=project)
    with pytest.raises(ValidationError) as error:
        expense.full_clean()
    assert "stage" in error.value.message_dict


def test_stage_deletion_preserves_expense_as_general_project_expense():
    stage = ProjectStageFactory()
    expense = ExpenseFactory(project=stage.project, stage=stage)
    expense.full_clean()
    assert stage.expenses.get() == expense
    project_id = expense.project_id
    stage.delete()
    expense.refresh_from_db()
    assert expense.stage is None and expense.project_id == project_id
    assert expense.amount == Decimal("100.00")


@pytest.mark.parametrize("status", ExpenseStatus.values)
def test_project_with_even_canceled_expense_is_protected(status):
    expense = ExpenseFactory(status=status)
    with pytest.raises(ProtectedError):
        expense.project.delete()
    assert Project.objects.filter(pk=expense.project_id).exists()
    expense.refresh_from_db()
    assert expense.status == status


def test_project_without_expenses_is_deletable():
    stage = ProjectStageFactory()
    project_id, stage_id = stage.project_id, stage.pk
    stage.project.delete()
    assert not Project.objects.filter(pk=project_id).exists()
    assert not ProjectStage.objects.filter(pk=stage_id).exists()


@pytest.mark.parametrize("relation", ["project", "stage"])
def test_database_enforces_foreign_keys(relation):
    expense = ExpenseFactory()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Expense.objects.filter(pk=expense.pk).update(
            **{f"{relation}_id": 9223372036854775807}
        )
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"
