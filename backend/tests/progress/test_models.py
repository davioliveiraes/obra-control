from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.progress.models import STAGE_PROGRESS_DATE_CONSTRAINT, StageProgressEntry
from apps.projects.models import ProjectStage
from tests.factories.progress import StageProgressEntryFactory
from tests.factories.projects import ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_defaults_decimal_and_timestamps_without_duplicated_context():
    entry = StageProgressEntryFactory()
    entry.full_clean()
    entry.refresh_from_db()
    assert entry.stage_id is not None and entry.progress_date == date(2026, 9, 9)
    assert isinstance(entry.progress_percentage, Decimal)
    assert entry.progress_percentage == Decimal("25.00") and entry.notes == ""
    created, updated = entry.created_at, entry.updated_at
    assert created is not None and updated >= created
    entry.notes = "Conferido em campo"
    entry.save()
    entry.refresh_from_db()
    assert entry.created_at == created and entry.updated_at > updated
    assert {field.name for field in StageProgressEntry._meta.fields} == {
        "id",
        "stage",
        "progress_date",
        "progress_percentage",
        "notes",
        "created_at",
        "updated_at",
    }
    assert "progress_percentage" not in {
        field.name for field in ProjectStage._meta.fields
    }


@pytest.mark.parametrize("field", ["stage", "progress_date", "progress_percentage"])
def test_required_fields_in_model_and_postgresql(field):
    entry = StageProgressEntryFactory.build(
        **{"stage": ProjectStageFactory(), field: None}
    )
    with pytest.raises(ValidationError) as error:
        entry.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError), transaction.atomic():
        entry.save()


@pytest.mark.parametrize("percentage", [Decimal("0.00"), Decimal("100.00")])
def test_inclusive_boundaries_are_valid(percentage):
    entry = StageProgressEntryFactory(progress_percentage=percentage)
    entry.full_clean()
    entry.refresh_from_db()
    assert entry.progress_percentage == percentage


@pytest.mark.parametrize("percentage", [Decimal("-0.01"), Decimal("100.01")])
def test_percentage_range_protected_by_postgresql(percentage):
    assert connection.vendor == "postgresql"
    entry = StageProgressEntryFactory()
    entry.progress_percentage = percentage
    with pytest.raises(ValidationError):
        entry.full_clean()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        StageProgressEntry.objects.filter(pk=entry.pk).update(
            progress_percentage=percentage
        )
    assert error.value.__cause__.diag.constraint_name == "progress_percentage_range"
    entry.refresh_from_db()
    assert entry.progress_percentage == Decimal("25.00")


@pytest.mark.parametrize("update", [False, True])
def test_stage_date_unique_in_postgresql_but_other_stages_allow_same_date(update):
    first = StageProgressEntryFactory()
    second = (
        StageProgressEntryFactory(stage=first.stage, progress_date=date(2026, 9, 10))
        if update
        else None
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        if update:
            StageProgressEntry.objects.filter(pk=second.pk).update(
                progress_date=first.progress_date
            )
        else:
            StageProgressEntryFactory(
                stage=first.stage, progress_date=first.progress_date
            )
    assert error.value.__cause__.diag.constraint_name == STAGE_PROGRESS_DATE_CONSTRAINT
    other = ProjectStageFactory(project=first.stage.project)
    assert (
        StageProgressEntryFactory(stage=other, progress_date=first.progress_date).stage
        != first.stage
    )
    if update:
        second.refresh_from_db()
        assert second.progress_date == date(2026, 9, 10)


@pytest.mark.parametrize("target", ["stage", "project"])
def test_progress_protects_stage_and_indirectly_project(target):
    entry = StageProgressEntryFactory()
    obj = entry.stage if target == "stage" else entry.stage.project
    with pytest.raises(ProtectedError):
        obj.delete()
    entry.refresh_from_db()
    obj.refresh_from_db()
    stage_id = entry.stage_id
    entry.delete()
    obj.delete()
    assert not ProjectStage.objects.filter(pk=stage_id).exists()
