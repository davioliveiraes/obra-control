from datetime import date

import factory

from apps.planning.models import StagePlan

from .projects import ProjectStageFactory


class StagePlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StagePlan

    stage = factory.SubFactory(ProjectStageFactory)
    planned_start_date = date(2026, 10, 1)
    planned_end_date = date(2026, 10, 20)
