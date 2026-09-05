import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from tests.factories.accounts import UserFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.projects import ProjectFactory


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user():
    return UserFactory(password="test-password")


@pytest.fixture
def authenticated_client(api_client, user):
    token = api_client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "test-password"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    token = api_client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    api_client.credentials(HTTP_X_CSRFTOKEN=token)
    return api_client


@pytest.fixture
def membership(user):
    return MembershipFactory(user=user, role=MembershipRole.OWNER)


@pytest.fixture
def tenant_client(authenticated_client, membership):
    response = authenticated_client.put(
        "/api/v1/organizations/current/",
        {"organization_id": membership.organization_id},
        format="json",
    )
    assert response.status_code == 200
    return authenticated_client


@pytest.fixture
def foreign_project():
    other = MembershipFactory()
    return ProjectFactory(organization=other.organization, name="Obra confidencial B")
