from django.urls import path

from .views import BudgetItemViewSet

app_name = "budgets"

urlpatterns = [
    path(
        "",
        BudgetItemViewSet.as_view({"get": "list", "post": "create"}),
        name="item-list",
    ),
    path(
        "<int:pk>/",
        BudgetItemViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="item-detail",
    ),
]
