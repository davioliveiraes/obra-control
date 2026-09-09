from datetime import date

import factory

from apps.daily_reports.models import DailyReport, DailyReportActivity

from .projects import ProjectFactory


class DailyReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyReport

    project = factory.SubFactory(ProjectFactory)
    report_date = date(2026, 9, 8)
    weather_notes = ""
    general_notes = ""


class DailyReportActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DailyReportActivity

    daily_report = factory.SubFactory(DailyReportFactory)
    stage = None
    description = "Organização geral do canteiro"
    position = 0
