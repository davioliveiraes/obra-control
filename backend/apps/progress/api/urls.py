from django.urls import path

from .views import StageProgressEntryViewSet

urlpatterns = [
    path(
        "",
        StageProgressEntryViewSet.as_view({"get": "list", "post": "create"}),
        name="stage-progress-list",
    ),
    path(
        "<int:pk>/",
        StageProgressEntryViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="stage-progress-detail",
    ),
]
