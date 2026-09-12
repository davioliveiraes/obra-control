"""Root URL configuration for ObraControl."""

from django.contrib import admin
from django.urls import include, path

from apps.progress.api.progress_summary_views import ProjectProgressSummaryView

api_v1_urlpatterns = [
    path("auth/", include("apps.accounts.api.urls")),
    path("organizations/", include("apps.organizations.api.urls")),
    path("customers/", include("apps.customers.api.urls")),
    path("projects/<int:project_id>/planning/", include("apps.planning.api.urls")),
    path("projects/<int:project_id>/budget/items/", include("apps.budgets.api.urls")),
    path("projects/<int:project_id>/", include("apps.finances.api.urls")),
    path(
        "projects/<int:project_id>/daily-reports/",
        include("apps.daily_reports.api.urls"),
    ),
    path(
        "projects/<int:project_id>/stages/<int:stage_id>/progress/",
        include("apps.progress.api.urls"),
    ),
    path(
        "projects/<int:project_id>/progress-summary/",
        ProjectProgressSummaryView.as_view(),
        name="project-progress-summary",
    ),
    path("projects/", include("apps.projects.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include((api_v1_urlpatterns, "api_v1"), namespace="api_v1"),
    ),
]
