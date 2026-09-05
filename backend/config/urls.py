"""Root URL configuration for ObraControl."""

from django.contrib import admin
from django.urls import include, path

api_v1_urlpatterns = []

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/v1/",
        include((api_v1_urlpatterns, "api_v1"), namespace="api_v1"),
    ),
]
