from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.planning.models import StagePlan
from apps.projects.models import ProjectStage
from tests.factories.planning import StagePlanFactory
from tests.factories.projects import ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_plan_has_single_stage_context_and_timestamps():
    stage = ProjectStageFactory()
    assert not StagePlan.objects.filter(stage=stage).exists()
    before = timezone.now()
    plan = StagePlanFactory(stage=stage)
    plan.full_clean()
    plan.refresh_from_db()
    assert stage.plan == plan
    assert plan.stage.project == stage.project
    assert before <= plan.created_at <= plan.updated_at <= timezone.now()
    assert timezone.is_aware(plan.created_at)
    assert {field.name for field in StagePlan._meta.fields} == {
        "id",
        "stage",
        "planned_start_date",
        "planned_end_date",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize("field", ["stage", "planned_start_date", "planned_end_date"])
def test_required_fields_validated_by_model_and_database(field):
    stage = ProjectStageFactory()
    plan = StagePlanFactory.build(
        stage=stage, **({field: None} if field != "stage" else {})
    )
    setattr(plan, field, None)
    with pytest.raises(ValidationError) as error:
        plan.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        plan.save()
    assert error.value.__cause__.diag.column_name == (
        "stage_id" if field == "stage" else field
    )


def test_database_enforces_stage_fk():
    stage = ProjectStageFactory()
    missing_id = stage.pk
    stage.delete()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        StagePlan.objects.create(
            stage_id=missing_id,
            planned_start_date=date(2026, 10, 1),
            planned_end_date=date(2026, 10, 20),
        )
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"


def test_one_to_one_prevents_duplicate_in_postgresql():
    plan = StagePlanFactory()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        StagePlanFactory(stage=plan.stage)
    assert error.value.__cause__.sqlstate == "23505"
    assert StagePlan.objects.filter(stage=plan.stage).count() == 1


@pytest.mark.parametrize("end", [date(2026, 10, 1), date(2026, 10, 20)])
def test_ordered_or_equal_dates_are_valid(end):
    plan = StagePlanFactory(planned_start_date=date(2026, 10, 1), planned_end_date=end)
    plan.full_clean()
    plan.refresh_from_db()
    assert plan.planned_end_date == end


@pytest.mark.parametrize("operation", ["create", "update"])
def test_database_rejects_reversed_dates_without_python_validation(operation):
    stage = ProjectStageFactory()
    original = StagePlanFactory(stage=stage) if operation == "update" else None
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        dates = {
            "planned_start_date": date(2026, 10, 20),
            "planned_end_date": date(2026, 10, 10),
        }
        if original is None:
            StagePlan.objects.create(stage=stage, **dates)
        else:
            StagePlan.objects.filter(pk=original.pk).update(**dates)
    assert (
        error.value.__cause__.diag.constraint_name
        == "planning_stageplan_planned_dates_order"
    )
    if original is not None:
        original.refresh_from_db()
        assert original.planned_start_date == date(2026, 10, 1)
        assert original.planned_end_date == date(2026, 10, 20)
    else:
        assert not StagePlan.objects.filter(stage=stage).exists()


@pytest.mark.parametrize("target", ["stage", "project"])
def test_cascade_removes_only_dependent_plans(target):
    plan = StagePlanFactory()
    foreign = StagePlanFactory()
    stage_id = plan.stage_id
    if target == "stage":
        plan.stage.delete()
    else:
        child = ProjectStageFactory(project=plan.stage.project, parent=plan.stage)
        StagePlanFactory(stage=child)
        plan.stage.project.delete()
    assert not ProjectStage.objects.filter(pk=stage_id).exists()
    assert StagePlan.objects.get() == foreign
