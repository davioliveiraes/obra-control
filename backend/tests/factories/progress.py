from datetime import date
from decimal import Decimal

import factory

from apps.progress.models import StageProgressEntry

from .projects import ProjectStageFactory


class StageProgressEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StageProgressEntry

    stage = factory.SubFactory(ProjectStageFactory)
    progress_date = date(2026, 9, 9)
    progress_percentage = Decimal("25.00")
    notes = ""
