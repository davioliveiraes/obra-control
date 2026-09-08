from django.urls import path

from .cost_summary_views import CostSummaryView
from .financial_summary_views import ProjectFinancialSummaryView
from .revenue_views import RevenueViewSet
from .views import ExpenseViewSet

app_name = "finances"

urlpatterns = [
    path(
        "expenses/",
        ExpenseViewSet.as_view({"get": "list", "post": "create"}),
        name="expense-list",
    ),
    path(
        "expenses/<int:pk>/",
        ExpenseViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="expense-detail",
    ),
    path("cost-summary/", CostSummaryView.as_view(), name="cost-summary"),
    path(
        "financial-summary/",
        ProjectFinancialSummaryView.as_view(),
        name="financial-summary",
    ),
    path(
        "revenues/",
        RevenueViewSet.as_view({"get": "list", "post": "create"}),
        name="revenue-list",
    ),
    path(
        "revenues/<int:pk>/",
        RevenueViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="revenue-detail",
    ),
]
