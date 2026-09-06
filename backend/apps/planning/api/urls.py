from django.urls import path

from .views import StagePlanViewSet

app_name = "planning"

urlpatterns = [
    path(
        "",
        StagePlanViewSet.as_view({"get": "list", "post": "create"}),
        name="plan-list",
    ),
    path(
        "<int:pk>/",
        StagePlanViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="plan-detail",
    ),
]
