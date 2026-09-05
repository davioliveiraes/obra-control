import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from tests.factories.accounts import UserFactory
from tests.factories.organizations import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/organizations/"
CURRENT_URL = "/api/v1/organizations/current/"
SESSION_KEY = "current_organization_id"
PASSWORD = "test-password"


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user():
    return UserFactory(password=PASSWORD)


@pytest.fixture
def authenticated_client(api_client, user):
    token = api_client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    token = api_client.get("/api/v1/auth/csrf/").json()["csrfToken"]
    api_client.credentials(HTTP_X_CSRFTOKEN=token)
    return api_client


def select_organization(client, organization_id):
    return client.put(CURRENT_URL, {"organization_id": organization_id}, format="json")


def representation(membership):
    return {
        "id": membership.organization_id,
        "name": membership.organization.name,
        "role": membership.role,
    }


def test_list_includes_only_current_users_active_memberships(
    authenticated_client, user
):
    own = MembershipFactory(user=user, role=MembershipRole.OWNER)
    other_user = MembershipFactory()
    MembershipFactory(user=user, is_active=False)
    OrganizationFactory()
    # Role must come from the requesting user's membership, not another member.
    MembershipFactory(organization=own.organization, role=MembershipRole.ADMIN)

    response = authenticated_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.json() == [representation(own)]
    assert other_user.organization_id not in [item["id"] for item in response.json()]
    assert SESSION_KEY not in authenticated_client.session
    assert "no-store" in response["Cache-Control"]


def test_user_without_memberships_gets_empty_list(authenticated_client):
    MembershipFactory()
    assert authenticated_client.get(LIST_URL).json() == []


@pytest.mark.parametrize("role", MembershipRole.values)
def test_selection_stores_only_organization_id_and_resolves_context(
    authenticated_client, user, role, django_assert_num_queries
):
    membership = MembershipFactory(user=user, role=role)
    session_before = dict(authenticated_client.session)
    selected = select_organization(authenticated_client, membership.organization_id)

    assert selected.status_code == 200
    assert selected.json() == representation(membership)
    assert dict(authenticated_client.session) == {
        **session_before,
        SESSION_KEY: membership.organization_id,
    }
    # Session + user + a single membership query joining its organization.
    with django_assert_num_queries(3):
        response = authenticated_client.get(CURRENT_URL)
    assert response.status_code == 200
    assert response.json() == representation(membership)
    assert response.wsgi_request.membership == membership
    assert response.wsgi_request.organization == membership.organization
    with django_assert_num_queries(0):
        assert (
            response.wsgi_request.membership.organization.name
            == membership.organization.name
        )


def test_no_context_is_selected_implicitly(
    authenticated_client, user, django_assert_num_queries
):
    MembershipFactory(user=user)
    # Only session and user; no membership lookup without explicit selection.
    with django_assert_num_queries(2):
        response = authenticated_client.get(CURRENT_URL)

    assert response.status_code == 404
    assert response.json() == {"detail": "Nenhuma organização selecionada."}
    assert response.wsgi_request.organization is None
    assert response.wsgi_request.membership is None
    assert SESSION_KEY not in authenticated_client.session


def test_invalid_selection_is_generic_and_preserves_valid_context(
    authenticated_client, user
):
    own = MembershipFactory(user=user)
    foreign = MembershipFactory()
    inactive = MembershipFactory(user=user, is_active=False)
    missing = OrganizationFactory()
    missing_id = missing.pk
    missing.delete()
    assert (
        select_organization(authenticated_client, own.organization_id).status_code
        == 200
    )

    for organization_id in [
        foreign.organization_id,
        inactive.organization_id,
        missing_id,
    ]:
        response = select_organization(authenticated_client, organization_id)
        assert response.status_code == 403
        assert response.json() == {"detail": "Organização indisponível."}
        assert authenticated_client.session[SESSION_KEY] == own.organization_id
        assert authenticated_client.get(CURRENT_URL).json() == representation(own)


def test_invalid_selection_does_not_create_context(authenticated_client):
    foreign = MembershipFactory()
    response = select_organization(authenticated_client, foreign.organization_id)
    assert response.status_code == 403
    assert SESSION_KEY not in authenticated_client.session
    assert authenticated_client.get(CURRENT_URL).status_code == 404


def test_django_superuser_does_not_bypass_membership_requirement(
    authenticated_client, user
):
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    foreign = MembershipFactory()

    assert authenticated_client.get(LIST_URL).json() == []
    assert (
        select_organization(authenticated_client, foreign.organization_id).status_code
        == 403
    )


def test_user_can_switch_between_own_organizations(authenticated_client, user):
    first = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    for membership in [first, second]:
        response = select_organization(authenticated_client, membership.organization_id)
        assert response.status_code == 200
        assert authenticated_client.session[SESSION_KEY] == membership.organization_id
        current = authenticated_client.get(CURRENT_URL)
        assert current.json() == representation(membership)
        assert current.wsgi_request.organization == membership.organization
        assert current.wsgi_request.membership == membership


def test_delete_context_keeps_user_authenticated_and_is_idempotent(
    authenticated_client, user
):
    membership = MembershipFactory(user=user)
    assert (
        select_organization(
            authenticated_client, membership.organization_id
        ).status_code
        == 200
    )

    for _ in range(2):
        response = authenticated_client.delete(CURRENT_URL)
        assert response.status_code == 204
        assert not response.content
        assert SESSION_KEY not in authenticated_client.session
        current = authenticated_client.get(CURRENT_URL)
        assert current.status_code == 404
        assert current.wsgi_request.organization is None
        assert current.wsgi_request.membership is None
        assert authenticated_client.get("/api/v1/auth/me/").json()["id"] == user.pk


@pytest.mark.parametrize("revocation", ["deactivate", "delete", "delete_organization"])
def test_revoked_membership_clears_context_on_next_request(
    authenticated_client, user, revocation
):
    membership = MembershipFactory(user=user)
    assert (
        select_organization(
            authenticated_client, membership.organization_id
        ).status_code
        == 200
    )
    if revocation == "deactivate":
        membership.is_active = False
        membership.save(update_fields=["is_active"])
    elif revocation == "delete":
        membership.delete()
    else:
        membership.organization.delete()

    # Even an endpoint outside organizations must exercise the middleware.
    response = authenticated_client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.wsgi_request.organization is None
    assert response.wsgi_request.membership is None
    assert SESSION_KEY not in authenticated_client.session
    current = authenticated_client.get(CURRENT_URL)
    assert current.status_code == 404
    assert current.json() == {"detail": "Nenhuma organização selecionada."}


def test_role_changes_are_reflected_without_reselecting(authenticated_client, user):
    membership = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    assert (
        select_organization(
            authenticated_client, membership.organization_id
        ).status_code
        == 200
    )
    membership.role = MembershipRole.ADMIN
    membership.save(update_fields=["role"])

    assert authenticated_client.get(CURRENT_URL).json() == representation(membership)
    assert authenticated_client.get(LIST_URL).json() == [representation(membership)]
    assert "role" not in authenticated_client.session


@pytest.mark.parametrize(
    "method, url",
    [
        ("get", LIST_URL),
        ("get", CURRENT_URL),
        ("put", CURRENT_URL),
        ("delete", CURRENT_URL),
    ],
)
def test_anonymous_requests_cannot_access_organization_endpoints(
    api_client, method, url, django_assert_num_queries
):
    with django_assert_num_queries(0):
        response = getattr(api_client, method)(url)
    assert response.status_code == 403
    assert response.wsgi_request.organization is None
    assert response.wsgi_request.membership is None


@pytest.mark.parametrize("method", ["put", "delete"])
def test_unsafe_operations_without_csrf_preserve_existing_context(
    authenticated_client, user, method
):
    own = MembershipFactory(user=user)
    other = MembershipFactory(user=user)
    assert (
        select_organization(authenticated_client, own.organization_id).status_code
        == 200
    )
    authenticated_client.credentials()

    response = getattr(authenticated_client, method)(
        CURRENT_URL, {"organization_id": other.organization_id}, format="json"
    )
    assert response.status_code == 403
    assert authenticated_client.session[SESSION_KEY] == own.organization_id
    assert authenticated_client.get(CURRENT_URL).json() == representation(own)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"organization_id": None},
        {"organization_id": "invalid"},
        {"organization_id": 0},
        {"organization_id": -1},
        {"organization_id": True},
        {"organization_id": 1.5},
        {"organization_id": 2**63},
    ],
)
def test_invalid_selection_payload_returns_400_without_creating_context(
    authenticated_client, payload
):
    response = authenticated_client.put(CURRENT_URL, payload, format="json")
    assert response.status_code == 400
    assert "organization_id" in response.json()
    assert SESSION_KEY not in authenticated_client.session


@pytest.mark.parametrize("value", [None, "invalid", "1", True, [], {}, -1, 2**63])
def test_malformed_session_id_is_cleared_without_server_error(
    authenticated_client, value
):
    # Seed invalid server-side session state deliberately, not an API bypass.
    session = authenticated_client.session
    session[SESSION_KEY] = value
    session.save()

    response = authenticated_client.get(CURRENT_URL)
    assert response.status_code == 404
    assert response.wsgi_request.organization is None
    assert response.wsgi_request.membership is None
    assert SESSION_KEY not in authenticated_client.session


def test_foreign_id_in_session_is_never_trusted(authenticated_client):
    foreign = MembershipFactory()
    session = authenticated_client.session
    session[SESSION_KEY] = foreign.organization_id
    session.save()

    response = authenticated_client.get(CURRENT_URL)
    assert response.status_code == 404
    assert response.wsgi_request.organization is None
    assert response.wsgi_request.membership is None
    assert SESSION_KEY not in authenticated_client.session


def test_logout_clears_selection_and_next_login_does_not_restore_it(
    authenticated_client, user
):
    membership = MembershipFactory(user=user)
    assert (
        select_organization(
            authenticated_client, membership.organization_id
        ).status_code
        == 200
    )
    assert authenticated_client.post("/api/v1/auth/logout/").status_code == 204
    assert SESSION_KEY not in authenticated_client.session
    assert authenticated_client.get(CURRENT_URL).status_code == 403

    assert (
        authenticated_client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": PASSWORD},
            format="json",
        ).status_code
        == 200
    )
    assert authenticated_client.get(CURRENT_URL).status_code == 404
    assert SESSION_KEY not in authenticated_client.session


def test_complete_selection_flow_preserves_context_after_cross_tenant_attempt(
    authenticated_client, user
):
    own = MembershipFactory(user=user)
    foreign = MembershipFactory()
    assert authenticated_client.get(LIST_URL).json() == [representation(own)]
    assert (
        select_organization(authenticated_client, own.organization_id).status_code
        == 200
    )
    assert authenticated_client.get(CURRENT_URL).json() == representation(own)
    assert (
        select_organization(authenticated_client, foreign.organization_id).status_code
        == 403
    )
    assert authenticated_client.get(CURRENT_URL).json() == representation(own)
    assert authenticated_client.delete(CURRENT_URL).status_code == 204
    assert authenticated_client.get(CURRENT_URL).status_code == 404
