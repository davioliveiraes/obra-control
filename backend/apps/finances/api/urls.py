from django.urls import path

from .cost_summary_views import CostSummaryView
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
]
