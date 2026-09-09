from django.urls import path

from .activity_views import DailyReportActivityViewSet
from .views import DailyReportViewSet

urlpatterns = [
    path(
        "",
        DailyReportViewSet.as_view({"get": "list", "post": "create"}),
        name="daily-report-list",
    ),
    path(
        "<int:pk>/",
        DailyReportViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="daily-report-detail",
    ),
    path(
        "<int:report_id>/activities/",
        DailyReportActivityViewSet.as_view({"get": "list", "post": "create"}),
        name="daily-report-activity-list",
    ),
    path(
        "<int:report_id>/activities/<int:pk>/",
        DailyReportActivityViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="daily-report-activity-detail",
    ),
]
