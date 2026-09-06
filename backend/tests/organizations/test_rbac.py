from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.organizations.models import Membership, MembershipRole
from apps.organizations.permissions import IsOrganizationAdminOrReadOnly
from tests.factories.accounts import UserFactory
from tests.factories.customers import CustomerFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.projects import ProjectFactory

pytestmark = pytest.mark.django_db
CURRENT_URL = "/api/v1/organizations/current/"
ROLE_DENIED = {"detail": "Seu papel na organização não permite esta operação."}


@pytest.fixture(
    params=[("customers", CustomerFactory), ("projects", ProjectFactory)],
    ids=["customers", "projects"],
)
def resource(request):
    name, factory = request.param
    return f"/api/v1/{name}/", factory


@pytest.fixture
def user():
    return UserFactory(password="test-password")


@pytest.fixture
def authenticated_client(user):
    client = APIClient(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    response = client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "test-password"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    client.credentials(HTTP_X_CSRFTOKEN=token)
    return client


def select_organization(client, membership):
    response = client.put(
        CURRENT_URL, {"organization_id": membership.organization_id}, format="json"
    )
    assert response.status_code == 200


@pytest.mark.parametrize("superuser", [False, True], ids=["member", "superuser-member"])
def test_member_is_read_only_even_for_django_superuser(
    authenticated_client, user, resource, superuser
):
    listing, factory = resource
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    # Keep the domain/factory default MEMBER, never promote it implicitly.
    membership = MembershipFactory(user=user)
    assert membership.role == MembershipRole.MEMBER
    own = factory(organization=membership.organization, name="Original")
    foreign = factory()
    select_organization(authenticated_client, membership)
    detail = f"{listing}{own.pk}/"
    model = type(own)
    before = model.objects.values().get(pk=own.pk)
    count_before = model.objects.count()

    response = authenticated_client.get(listing)
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert [item["id"] for item in response.json()["results"]] == [own.pk]
    assert authenticated_client.get(detail).status_code == 200
    assert authenticated_client.get(f"{listing}{foreign.pk}/").status_code == 404
    for url in [listing, detail]:
        assert authenticated_client.head(url).status_code == 200
        options = authenticated_client.options(url)
        assert options.status_code == 200
        assert "PUT" not in options["Allow"]

    for method in ["post", "patch", "delete"]:
        url = listing if method == "post" else detail
        response = getattr(authenticated_client, method)(
            url, {"name": "Negado"}, format="json"
        )
        assert response.status_code == 403
        assert response.json() == ROLE_DENIED  # CSRF is valid; denial is by role.
        own.refresh_from_db()
        assert own.name == "Original"
        assert model.objects.values().get(pk=own.pk) == before
        assert model.objects.count() == count_before
    assert "role" not in authenticated_client.session


def test_admin_downgrade_revokes_writes_without_relogin_or_reselection(
    authenticated_client, user, resource
):
    listing, factory = resource
    membership = MembershipFactory(user=user, role=MembershipRole.ADMIN)
    select_organization(authenticated_client, membership)
    response = authenticated_client.post(listing, {"name": "Permitido"}, format="json")
    assert response.status_code == 201
    own = factory._meta.model.objects.get(pk=response.json()["id"])
    detail = f"{listing}{own.pk}/"
    session_before = dict(authenticated_client.session)
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])

    response = authenticated_client.patch(detail, {"name": "Negado"}, format="json")
    assert response.status_code == 403
    assert response.json() == ROLE_DENIED
    assert response.wsgi_request.membership.role == MembershipRole.MEMBER
    own.refresh_from_db()
    assert own.name == "Permitido"
    assert authenticated_client.get(detail).status_code == 200
    assert dict(authenticated_client.session) == session_before
    assert "role" not in session_before


def test_switching_tenant_switches_effective_role(authenticated_client, user, resource):
    listing, factory = resource
    owner = MembershipFactory(user=user, role=MembershipRole.OWNER)
    member = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    second = factory(organization=member.organization)
    select_organization(authenticated_client, owner)
    response = authenticated_client.post(
        listing, {"name": "Criado em A"}, format="json"
    )
    assert response.status_code == 201
    first_id = response.json()["id"]
    select_organization(authenticated_client, member)

    before = type(second).objects.count()
    response = authenticated_client.post(
        listing, {"name": "Negado em B"}, format="json"
    )
    assert response.status_code == 403
    assert response.json() == ROLE_DENIED
    assert type(second).objects.count() == before
    response = authenticated_client.get(listing)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [second.pk]
    assert response.wsgi_request.membership == member
    assert authenticated_client.get(f"{listing}{first_id}/").status_code == 404
    assert "role" not in authenticated_client.session
    select_organization(authenticated_client, owner)
    assert (
        authenticated_client.patch(
            f"{listing}{first_id}/", {"name": "Escrita restaurada em A"}, format="json"
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", [MembershipRole.ADMIN, MembershipRole.MEMBER])
def test_cross_tenant_and_missing_ids_do_not_leak_existence(
    authenticated_client, user, resource, role
):
    listing, factory = resource
    membership = MembershipFactory(user=user, role=role)
    select_organization(authenticated_client, membership)
    own = factory(organization=membership.organization)
    foreign = factory()
    model = type(own)
    before = list(model.objects.order_by("pk").values())
    for method in ["get", "patch", "delete"]:
        response = getattr(authenticated_client, method)(
            f"{listing}{foreign.pk}/", {"name": "Negado"}, format="json"
        )
        missing = getattr(authenticated_client, method)(
            f"{listing}9223372036854775807/", {"name": "Negado"}, format="json"
        )
        expected = 403 if role == MembershipRole.MEMBER and method != "get" else 404
        assert response.status_code == missing.status_code == expected
        assert response.json() == missing.json()
    assert list(model.objects.order_by("pk").values()) == before


def test_role_permission_uses_resolved_membership_without_queries(
    django_assert_num_queries,
):
    permission = IsOrganizationAdminOrReadOnly()
    cases = [
        (None, "GET", False),
        (Membership(role=MembershipRole.MEMBER), "GET", True),
        (Membership(role=MembershipRole.MEMBER), "POST", False),
        (Membership(role=MembershipRole.OWNER), "POST", True),
        (Membership(role=MembershipRole.ADMIN), "POST", True),
    ]
    with django_assert_num_queries(0):
        for membership, method, expected in cases:
            request = SimpleNamespace(membership=membership, method=method)
            assert permission.has_permission(request, None) is expected
