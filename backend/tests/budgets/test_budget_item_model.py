from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.budgets.models import BudgetItem
from apps.projects.models import ProjectStage
from tests.factories.budgets import BudgetItemFactory
from tests.factories.projects import ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_item_fields_context_and_timestamps():
    before = timezone.now()
    item = BudgetItemFactory()
    item.full_clean()
    item.refresh_from_db()
    assert item.stage.budget_items.get() == item
    assert isinstance(item.quantity, Decimal) and isinstance(item.unit_price, Decimal)
    assert before <= item.created_at <= item.updated_at <= timezone.now()
    assert timezone.is_aware(item.created_at)
    assert {field.name for field in BudgetItem._meta.fields} == {
        "id",
        "stage",
        "description",
        "unit",
        "quantity",
        "unit_price",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    "field", ["stage", "description", "unit", "quantity", "unit_price"]
)
def test_required_fields_in_model_and_database(field):
    item = BudgetItemFactory.build(stage=ProjectStageFactory())
    setattr(item, field, None)
    with pytest.raises(ValidationError) as error:
        item.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        item.save()
    assert error.value.__cause__.diag.column_name == (
        "stage_id" if field == "stage" else field
    )


@pytest.mark.parametrize("field", ["description", "unit"])
def test_model_rejects_blank_text(field):
    item = BudgetItemFactory.build(stage=ProjectStageFactory(), **{field: ""})
    with pytest.raises(ValidationError) as error:
        item.full_clean()
    assert field in error.value.message_dict


def test_stage_fk_enforced_in_database():
    stage = ProjectStageFactory()
    stage_id = stage.pk
    stage.delete()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        BudgetItem.objects.create(
            stage_id=stage_id,
            description="Item",
            unit="un",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
        )
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"


def test_multiple_equal_items_per_stage_and_across_stages_are_allowed():
    first = BudgetItemFactory(description="Concreto")
    second = BudgetItemFactory(stage=first.stage, description=first.description)
    third = BudgetItemFactory(description=first.description)
    assert first.stage.budget_items.count() == 2
    assert len({first.pk, second.pk, third.pk}) == 3


@pytest.mark.parametrize(
    "field,value,constraint",
    [
        ("quantity", "0", "budgets_budgetitem_quantity_positive"),
        ("quantity", "-1", "budgets_budgetitem_quantity_positive"),
        ("quantity", "-0.0001", "budgets_budgetitem_quantity_positive"),
        ("unit_price", "-0.01", "budgets_budgetitem_unit_price_nonnegative"),
    ],
)
def test_numeric_rules_in_model_and_postgresql(field, value, constraint):
    item = BudgetItemFactory()
    invalid = BudgetItemFactory.build(stage=item.stage, **{field: Decimal(value)})
    with pytest.raises(ValidationError):
        invalid.full_clean()
    before = BudgetItem.objects.values().get(pk=item.pk)
    # Neither save nor QuerySet.update calls full_clean automatically.
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        invalid.save()
    assert error.value.__cause__.diag.constraint_name == constraint
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        BudgetItem.objects.filter(pk=item.pk).update(**{field: Decimal(value)})
    assert error.value.__cause__.diag.constraint_name == constraint
    item.refresh_from_db()
    assert BudgetItem.objects.values().get(pk=item.pk) == before


def test_smallest_quantity_and_zero_price_are_valid():
    item = BudgetItemFactory(quantity=Decimal("0.0001"), unit_price=Decimal("0.00"))
    item.full_clean()
    item.refresh_from_db()
    assert item.quantity == Decimal("0.0001")
    assert item.unit_price == Decimal("0.00")
    assert item.total == Decimal("0")


@pytest.mark.parametrize("target", ["stage", "project"])
def test_cascade_removes_items_only_from_deleted_context(target):
    item = BudgetItemFactory()
    BudgetItemFactory(stage=item.stage)
    foreign = BudgetItemFactory()
    stage_id = item.stage_id
    if target == "stage":
        item.stage.delete()
    else:
        BudgetItemFactory(
            stage=ProjectStageFactory(project=item.stage.project, parent=item.stage)
        )
        item.stage.project.delete()
    assert not ProjectStage.objects.filter(pk=stage_id).exists()
    assert BudgetItem.objects.get() == foreign
