from django.urls import path
from rest_framework.routers import SimpleRouter

from .stage_views import ProjectStageViewSet
from .views import ProjectViewSet

app_name = "projects"

router = SimpleRouter()
router.register("", ProjectViewSet, basename="project")
urlpatterns = [
    path(
        "<int:project_id>/stages/",
        ProjectStageViewSet.as_view({"get": "list", "post": "create"}),
        name="stage-list",
    ),
    path(
        "<int:project_id>/stages/<int:pk>/",
        ProjectStageViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="stage-detail",
    ),
    *router.urls,
]
