from django.urls import path

from .views import ExpenseViewSet

app_name = "finances"

urlpatterns = [
    path(
        "",
        ExpenseViewSet.as_view({"get": "list", "post": "create"}),
        name="expense-list",
    ),
    path(
        "<int:pk>/",
        ExpenseViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="expense-detail",
    ),
]
