from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import connection

from apps.progress.models import StageProgressEntry
from apps.progress.services.progress_summary import get_project_progress_summary
from tests.factories.progress import StageProgressEntryFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
AS_OF = date(2026, 9, 12)


def expected_row(stage, entry=None):
    return {
        "stage_id": stage.pk,
        "progress_entry_id": entry.pk if entry is not None else None,
        "progress_date": entry.progress_date if entry is not None else None,
        "progress_percentage": (
            entry.progress_percentage if entry is not None else None
        ),
    }


def test_project_without_stages_and_stage_without_history():
    project = ProjectFactory()
    assert get_project_progress_summary(project, as_of_date=AS_OF) == {
        "project_id": project.pk,
        "as_of_date": AS_OF,
        "stages": [],
    }
    stage = ProjectStageFactory(project=project)
    assert get_project_progress_summary(project, as_of_date=AS_OF) == {
        "project_id": project.pk,
        "as_of_date": AS_OF,
        "stages": [expected_row(stage)],
    }


@pytest.mark.parametrize("percentage", ["0.00", "100.00", "33.33", "62.50"])
def test_explicit_percentages_preserve_decimal_including_zero(percentage):
    entry = StageProgressEntryFactory(progress_percentage=Decimal(percentage))
    row = get_project_progress_summary(entry.stage.project, as_of_date=AS_OF)["stages"][
        0
    ]
    assert row == expected_row(entry.stage, entry)
    assert isinstance(row["progress_percentage"], Decimal)
    assert row["progress_percentage"].as_tuple().exponent == -2


def test_latest_eligible_date_wins_not_creation_edit_id_or_highest_percentage():
    stage = ProjectStageFactory()
    StageProgressEntryFactory(
        stage=stage,
        progress_date=date(2026, 9, 9),
        progress_percentage=Decimal("70.00"),
    )
    latest = StageProgressEntryFactory(
        stage=stage,
        progress_date=date(2026, 9, 10),
        progress_percentage=Decimal("68.00"),
    )
    retroactive = StageProgressEntryFactory(
        stage=stage,
        progress_date=date(2026, 9, 5),
        progress_percentage=Decimal("99.99"),
    )
    assert retroactive.pk > latest.pk
    assert retroactive.created_at > latest.created_at
    assert get_project_progress_summary(stage.project, as_of_date=AS_OF)["stages"] == [
        expected_row(stage, latest)
    ]

    with patch(
        "django.utils.timezone.now", return_value=latest.updated_at + timedelta(days=1)
    ):
        retroactive.progress_percentage = Decimal("100.00")
        retroactive.save()
    assert retroactive.updated_at > latest.updated_at
    assert get_project_progress_summary(stage.project, as_of_date=AS_OF)["stages"] == [
        expected_row(stage, latest)
    ]


def test_reference_date_is_inclusive_future_is_excluded_and_only_future_is_null():
    stage = ProjectStageFactory()
    on_date = StageProgressEntryFactory(stage=stage, progress_date=AS_OF)
    future = StageProgressEntryFactory(
        stage=stage,
        progress_date=AS_OF + timedelta(days=1),
        progress_percentage=Decimal("100.00"),
    )
    future_only = ProjectStageFactory(project=stage.project)
    StageProgressEntryFactory(stage=future_only, progress_date=future.progress_date)
    assert get_project_progress_summary(stage.project, as_of_date=AS_OF)["stages"] == [
        expected_row(stage, on_date),
        expected_row(future_only),
    ]


def test_same_history_with_explicit_reference_dates_is_read_only():
    stage = ProjectStageFactory()
    first = StageProgressEntryFactory(stage=stage, progress_date=date(2026, 9, 9))
    second = StageProgressEntryFactory(
        stage=stage,
        progress_date=date(2026, 9, 12),
        progress_percentage=Decimal("62.50"),
    )
    before = list(StageProgressEntry.objects.order_by("pk").values())
    for reference, selected in [
        (date(2026, 9, 8), None),
        (date(2026, 9, 9), first),
        (date(2026, 9, 11), first),
        (date(2026, 9, 12), second),
    ]:
        result = get_project_progress_summary(stage.project, as_of_date=reference)
        assert result["as_of_date"] == reference
        assert isinstance(result["as_of_date"], date)
        assert result["stages"] == [expected_row(stage, selected)]
    assert list(StageProgressEntry.objects.order_by("pk").values()) == before


def test_parent_does_not_inherit_children_but_can_have_its_own_entry():
    parent = ProjectStageFactory()
    children = [
        ProjectStageFactory(project=parent.project, parent=parent) for _ in range(2)
    ]
    entries = [
        StageProgressEntryFactory(stage=child, progress_percentage=Decimal(percentage))
        for child, percentage in zip(children, ["100.00", "50.00"], strict=True)
    ]
    expected = [expected_row(parent)] + [
        expected_row(child, entry)
        for child, entry in zip(children, entries, strict=True)
    ]
    assert (
        get_project_progress_summary(parent.project, as_of_date=AS_OF)["stages"]
        == expected
    )
    own = StageProgressEntryFactory(stage=parent, progress_percentage=Decimal("33.33"))
    expected[0] = expected_row(parent, own)
    assert (
        get_project_progress_summary(parent.project, as_of_date=AS_OF)["stages"]
        == expected
    )


def test_one_row_per_stage_ordered_by_position_then_id_and_scoped_to_project():
    project = ProjectFactory()
    stages = [
        ProjectStageFactory(project=project, position=position)
        for position in [2, 0, 1, 0]
    ]
    own = StageProgressEntryFactory(stage=stages[1])
    for other in [ProjectFactory(organization=project.organization), ProjectFactory()]:
        StageProgressEntryFactory(stage=ProjectStageFactory(project=other))
    assert get_project_progress_summary(project, as_of_date=AS_OF)["stages"] == [
        expected_row(stages[1], own),
        expected_row(stages[3]),
        expected_row(stages[2]),
        expected_row(stages[0]),
    ]


@pytest.mark.parametrize("stage_count", [0, 1, 30])
def test_one_materialized_sql_query_independent_of_stage_and_history_count(
    stage_count, django_assert_num_queries
):
    assert connection.vendor == "postgresql"
    project = ProjectFactory()
    expected = []
    for _ in range(stage_count):
        stage = ProjectStageFactory(project=project)
        for day in [10, 12, 13]:
            entry = StageProgressEntryFactory(
                stage=stage, progress_date=date(2026, 9, day)
            )
            if day == 12:
                expected.append(expected_row(stage, entry))
    # Measure only the service, not fixtures, sessions, Membership or Project lookup.
    with django_assert_num_queries(1) as captured:
        result = get_project_progress_summary(project, as_of_date=AS_OF)
    # Returned data must already be materialized, with no deferred queries on access.
    with django_assert_num_queries(0):
        assert isinstance(result, dict) and isinstance(result["stages"], list)
        assert result["stages"] == expected
    sql = captured.captured_queries[0]["sql"].upper()
    assert sql.lstrip().startswith("SELECT")
    assert "PROJECTS_PROJECTSTAGE" in sql and "PROGRESS_STAGEPROGRESSENTRY" in sql
    assert not any(
        name in sql for name in ["PLANNING_", "BUDGETS_", "FINANCES_", "DAILY_REPORTS_"]
    )
