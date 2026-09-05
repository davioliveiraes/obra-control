"""Root URL configuration for ObraControl."""

from django.contrib import admin
from django.urls import include, path

api_v1_urlpatterns = [
    path("auth/", include("apps.accounts.api.urls")),
    path("organizations/", include("apps.organizations.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include((api_v1_urlpatterns, "api_v1"), namespace="api_v1"),
    ),
]
