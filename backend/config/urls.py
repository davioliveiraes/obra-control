"""Root URL configuration for ObraControl."""

from django.contrib import admin
from django.urls import include, path

api_v1_urlpatterns = [
    path("auth/", include("apps.accounts.api.urls")),
    path("organizations/", include("apps.organizations.api.urls")),
    path("customers/", include("apps.customers.api.urls")),
    path("projects/<int:project_id>/planning/", include("apps.planning.api.urls")),
    path("projects/", include("apps.projects.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include((api_v1_urlpatterns, "api_v1"), namespace="api_v1"),
    ),
]
