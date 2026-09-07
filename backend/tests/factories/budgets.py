from decimal import Decimal

import factory

from apps.budgets.models import BudgetItem

from .projects import ProjectStageFactory


class BudgetItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BudgetItem

    stage = factory.SubFactory(ProjectStageFactory)
    description = factory.Sequence(lambda number: f"Item previsto {number}")
    unit = "un"
    quantity = Decimal("1.0000")
    unit_price = Decimal("10.00")
