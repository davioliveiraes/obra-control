from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.daily_reports.models import (
    DAILY_REPORT_DATE_CONSTRAINT,
    DailyReport,
    DailyReportActivity,
)
from apps.projects.models import Project
from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_report_defaults_required_context_and_timestamps():
    report = DailyReportFactory()
    report.full_clean()
    assert report.project_id is not None
    assert report.report_date == date(2026, 9, 8)
    assert report.weather_notes == report.general_notes == ""
    assert report.created_at is not None and report.updated_at >= report.created_at
    original_created, original_updated = report.created_at, report.updated_at
    report.general_notes = "Registro retroativo"
    report.save()
    report.refresh_from_db()
    assert (
        report.created_at == original_created and report.updated_at > original_updated
    )
    assert {field.name for field in DailyReport._meta.fields} == {
        "id",
        "project",
        "report_date",
        "weather_notes",
        "general_notes",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize("field", ["project", "report_date"])
def test_report_required_fields_in_model_and_postgresql(field):
    report = DailyReportFactory.build(**{"project": ProjectFactory(), field: None})
    with pytest.raises(ValidationError) as error:
        report.full_clean()
    assert field in error.value.message_dict
    with pytest.raises(IntegrityError), transaction.atomic():
        report.save()


@pytest.mark.parametrize("update", [False, True])
def test_report_unique_project_date_in_postgresql(update):
    assert connection.vendor == "postgresql"
    first = DailyReportFactory()
    second = (
        DailyReportFactory(project=first.project, report_date=date(2026, 9, 9))
        if update
        else None
    )
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        if update:
            DailyReport.objects.filter(pk=second.pk).update(
                report_date=first.report_date
            )
        else:
            DailyReportFactory(project=first.project, report_date=first.report_date)
    assert error.value.__cause__.diag.constraint_name == DAILY_REPORT_DATE_CONSTRAINT
    assert (
        DailyReportFactory(report_date=first.report_date).project_id != first.project_id
    )
    if update:
        second.refresh_from_db()
        assert second.report_date == date(2026, 9, 9)


def test_report_protects_project_until_explicitly_deleted():
    activity = DailyReportActivityFactory()
    report, project = activity.daily_report, activity.daily_report.project
    with pytest.raises(ProtectedError):
        project.delete()
    assert DailyReportActivity.objects.filter(pk=activity.pk).exists()
    report.delete()
    assert not DailyReportActivity.objects.exists()
    project_id = project.pk
    project.delete()
    assert not Project.objects.filter(pk=project_id).exists()


def test_activity_defaults_stage_validation_and_timestamps():
    activity = DailyReportActivityFactory()
    activity.full_clean()
    assert activity.stage is None and activity.position == 0
    assert activity.created_at and activity.updated_at >= activity.created_at
    created, updated = activity.created_at, activity.updated_at
    activity.stage = ProjectStageFactory(project=activity.daily_report.project)
    activity.full_clean()
    activity.save()
    activity.refresh_from_db()
    assert activity.created_at == created and activity.updated_at > updated
    assert {field.name for field in DailyReportActivity._meta.fields} == {
        "id",
        "daily_report",
        "stage",
        "description",
        "position",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    "field,value", [("daily_report", None), ("description", ""), ("position", -1)]
)
def test_activity_model_rejects_invalid_required_values(field, value):
    activity = DailyReportActivityFactory.build(**{field: value})
    with pytest.raises(ValidationError) as error:
        activity.full_clean()
    assert field in error.value.message_dict


@pytest.mark.parametrize("field,value", [("daily_report", None), ("position", -1)])
def test_activity_postgresql_required_fk_and_positive_position(field, value):
    report = DailyReportFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        DailyReportActivityFactory(**{"daily_report": report, field: value})


@pytest.mark.parametrize("other_tenant", [False, True])
def test_activity_clean_rejects_other_project_stage(other_tenant):
    activity = DailyReportActivityFactory()
    project = (
        ProjectFactory()
        if other_tenant
        else ProjectFactory(organization=activity.daily_report.project.organization)
    )
    activity.stage = ProjectStageFactory(project=project)
    with pytest.raises(ValidationError) as error:
        activity.full_clean()
    assert "stage" in error.value.message_dict


def test_stage_delete_preserves_activity_and_report():
    report = DailyReportFactory()
    stage = ProjectStageFactory(project=report.project)
    activity = DailyReportActivityFactory(daily_report=report, stage=stage)
    before = DailyReportActivity.objects.values().get(pk=activity.pk)
    stage.delete()
    activity.refresh_from_db()
    assert activity.stage is None
    assert DailyReportActivity.objects.values().get(pk=activity.pk) == {
        **before,
        "stage_id": None,
    }
    report.refresh_from_db()
