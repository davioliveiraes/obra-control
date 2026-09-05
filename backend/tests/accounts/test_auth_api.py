import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.accounts import UserFactory
from tests.factories.organizations import MembershipFactory

pytestmark = pytest.mark.django_db

PASSWORD = "  test-password  "


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user():
    return UserFactory(password=PASSWORD, first_name="Ana", last_name="Silva")


def csrf_token(client):
    response = client.get(reverse("api_v1:auth:csrf"))
    assert response.status_code == 200
    return response.json()["csrfToken"]


def login_user(client, user, *, email=None):
    return client.post(
        reverse("api_v1:auth:login"),
        {"email": email or user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token(client),
    )


def identity(user):
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def test_public_csrf_endpoint_sets_cookie_and_returns_masked_token(api_client):
    response = api_client.get("/api/v1/auth/csrf/")

    assert response.status_code == 200
    assert set(response.json()) == {"csrfToken"}
    cookie = response.cookies[settings.CSRF_COOKIE_NAME]
    assert cookie.value
    assert response.json()["csrfToken"] != cookie.value
    assert cookie["samesite"] == "Lax"
    assert not cookie["secure"]
    assert "no-store" in response["Cache-Control"]
    assert "Cookie" in response["Vary"]


@pytest.mark.parametrize("with_cookie", [False, True])
def test_anonymous_login_requires_csrf_header_even_with_valid_credentials(
    api_client, user, with_cookie
):
    if with_cookie:
        csrf_token(api_client)
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
    )

    assert response.status_code == 403
    assert api_client.get("/api/v1/auth/me/").status_code == 403
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_login_rejects_csrf_token_from_another_client(api_client, user):
    csrf_token(api_client)
    foreign_token = csrf_token(APIClient(enforce_csrf_checks=True))
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=foreign_token,
    )
    assert response.status_code == 403
    assert api_client.get("/api/v1/auth/me/").status_code == 403


def test_login_rejects_untrusted_origin_even_with_matching_csrf(api_client, user):
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token(api_client),
        HTTP_ORIGIN="https://untrusted.example",
    )
    assert response.status_code == 403
    assert api_client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.parametrize("normalize", [False, True])
def test_login_sets_session_cookie_and_returns_only_identity(
    api_client, user, normalize
):
    email = f"  {user.email.upper()}  " if normalize else user.email
    response = login_user(api_client, user, email=email)

    assert response.status_code == 200
    assert response.json() == identity(user)
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie.value
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert not cookie["secure"]
    assert "no-store" in response["Cache-Control"]
    assert api_client.get("/api/v1/auth/me/").json() == identity(user)


def test_wrong_password_and_unknown_email_have_same_generic_response(api_client, user):
    token = csrf_token(api_client)
    responses = [
        api_client.post(
            "/api/v1/auth/login/",
            credentials,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        for credentials in [
            {"email": user.email, "password": "wrong-password"},
            {"email": "missing@example.com", "password": PASSWORD},
        ]
    ]

    for response in responses:
        assert response.status_code == 400
        assert response.json() == {"detail": "Credenciais inválidas."}
        assert settings.SESSION_COOKIE_NAME not in response.cookies
    assert api_client.get("/api/v1/auth/me/").status_code == 403


def test_inactive_user_cannot_login(api_client):
    user = UserFactory(password=PASSWORD, is_active=False)
    response = login_user(api_client, user)
    assert response.status_code == 400
    assert response.json() == {"detail": "Credenciais inválidas."}
    assert api_client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "email"),
        ({"email": "user@example.com"}, "password"),
        ({"email": "invalid", "password": PASSWORD}, "email"),
        ({"email": "user@example.com", "password": ""}, "password"),
    ],
)
def test_login_validates_payload_without_echoing_password(api_client, payload, field):
    response = api_client.post(
        "/api/v1/auth/login/",
        payload,
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token(api_client),
    )
    assert response.status_code == 400
    assert field in response.json()
    assert PASSWORD not in response.content.decode()
    assert settings.SESSION_COOKIE_NAME not in response.cookies


def test_me_requires_authentication(api_client):
    assert api_client.get("/api/v1/auth/me/").status_code == 403


def test_me_returns_no_memberships_or_privileges(api_client, user):
    MembershipFactory.create_batch(2, user=user)
    assert login_user(api_client, user).status_code == 200
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 200
    assert response.json() == identity(user)
    assert "no-store" in response["Cache-Control"]


def test_logout_requires_authentication_even_with_csrf(api_client):
    response = api_client.post(
        "/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token(api_client)
    )
    assert response.status_code == 403


def test_authenticated_logout_without_csrf_is_rejected(api_client, user):
    assert login_user(api_client, user).status_code == 200
    response = api_client.post("/api/v1/auth/logout/")

    assert response.status_code == 403
    assert api_client.get("/api/v1/auth/me/").json() == identity(user)


def test_login_rotates_csrf_and_old_token_cannot_logout(api_client, user):
    old_token = csrf_token(api_client)
    response = api_client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=old_token,
    )
    assert response.status_code == 200
    assert (
        api_client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=old_token).status_code
        == 403
    )
    assert api_client.get("/api/v1/auth/me/").status_code == 200
    assert (
        api_client.post(
            "/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token(api_client)
        ).status_code
        == 204
    )


def test_complete_http_flow_and_old_session_cannot_be_reused_after_logout(
    api_client, user
):
    assert login_user(api_client, user).status_code == 200
    assert api_client.get("/api/v1/auth/me/").json() == identity(user)
    old_session = api_client.cookies[settings.SESSION_COOKIE_NAME].value

    response = api_client.post(
        "/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token(api_client)
    )
    assert response.status_code == 204
    assert not response.content
    assert api_client.get("/api/v1/auth/me/").status_code == 403

    replay_client = APIClient(enforce_csrf_checks=True)
    replay_client.cookies[settings.SESSION_COOKIE_NAME] = old_session
    assert replay_client.get("/api/v1/auth/me/").status_code == 403


def test_login_as_different_identity_replaces_previous_session(api_client, user):
    assert login_user(api_client, user).status_code == 200
    old_session = api_client.cookies[settings.SESSION_COOKIE_NAME].value
    other = UserFactory(password=PASSWORD)
    assert login_user(api_client, other).status_code == 200

    assert api_client.cookies[settings.SESSION_COOKIE_NAME].value != old_session
    assert api_client.get("/api/v1/auth/me/").json() == identity(other)
    replay_client = APIClient(enforce_csrf_checks=True)
    replay_client.cookies[settings.SESSION_COOKIE_NAME] = old_session
    assert replay_client.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.parametrize("endpoint", ["login", "logout"])
def test_get_cannot_login_or_logout(api_client, user, endpoint):
    assert login_user(api_client, user).status_code == 200
    assert api_client.get(f"/api/v1/auth/{endpoint}/").status_code == 405
    assert api_client.get("/api/v1/auth/me/").json() == identity(user)


def test_deactivated_user_is_not_recognized_by_existing_session(api_client, user):
    assert login_user(api_client, user).status_code == 200
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert api_client.get("/api/v1/auth/me/").status_code == 403
