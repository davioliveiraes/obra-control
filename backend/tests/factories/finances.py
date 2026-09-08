from datetime import date
from decimal import Decimal

import factory

from apps.finances.models import Expense, ExpenseStatus, Revenue, RevenueStatus

from .projects import ProjectFactory


class ExpenseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Expense

    project = factory.SubFactory(ProjectFactory)
    stage = None
    description = "Expense"
    amount = Decimal("100.00")
    expense_date = date(2026, 9, 6)
    status = ExpenseStatus.ACTIVE


class RevenueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Revenue

    project = factory.SubFactory(ProjectFactory)
    description = "Revenue"
    amount = Decimal("100.00")
    revenue_date = date(2026, 9, 5)
    status = RevenueStatus.ACTIVE
    notes = ""
