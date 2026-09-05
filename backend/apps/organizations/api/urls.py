from django.urls import path

from .views import CurrentOrganizationView, OrganizationListView

app_name = "organizations"

urlpatterns = [
    path("", OrganizationListView.as_view(), name="list"),
    path("current/", CurrentOrganizationView.as_view(), name="current"),
]
