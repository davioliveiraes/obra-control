import pytest
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.organizations.models import MembershipRole
from tests.factories.accounts import UserFactory
from tests.factories.customers import CustomerFactory
from tests.factories.organizations import MembershipFactory

pytestmark = pytest.mark.django_db
LIST_URL = "/api/v1/customers/"
CURRENT_URL = "/api/v1/organizations/current/"
PASSWORD = "test-password"
CUSTOMER_FIELDS = {"id", "name", "email", "phone", "created_at", "updated_at"}


def detail_url(customer):
    return f"{LIST_URL}{customer.pk}/"


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


@pytest.fixture
def membership(user):
    return MembershipFactory(user=user, role=MembershipRole.OWNER)


@pytest.fixture
def tenant_client(authenticated_client, membership):
    response = authenticated_client.put(
        CURRENT_URL, {"organization_id": membership.organization_id}, format="json"
    )
    assert response.status_code == 200
    return authenticated_client


@pytest.fixture
def foreign_customer():
    other = MembershipFactory()
    return CustomerFactory(
        organization=other.organization, name="Cliente confidencial B"
    )


def test_list_is_scoped_and_does_not_leak_count_or_customers(
    tenant_client, membership, foreign_customer
):
    first = CustomerFactory(organization=membership.organization, name="Cliente A1")
    second = CustomerFactory(organization=membership.organization, name="Cliente A2")

    response = tenant_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [item["id"] for item in response.json()["results"]] == [first.pk, second.pk]
    assert foreign_customer.name not in response.content.decode()
    assert all(set(item) == CUSTOMER_FIELDS for item in response.json()["results"])
    assert "no-store" in response["Cache-Control"]


def test_get_cross_tenant_returns_same_404_as_missing_id(
    tenant_client, foreign_customer
):
    response = tenant_client.get(detail_url(foreign_customer))
    missing = tenant_client.get(f"{LIST_URL}9223372036854775807/")
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    assert foreign_customer.name not in response.content.decode()


def test_patch_cross_tenant_returns_404_and_preserves_database(
    tenant_client, membership, foreign_customer
):
    own = CustomerFactory(organization=membership.organization)
    before = list(Customer.objects.order_by("pk").values())
    response = tenant_client.patch(
        detail_url(foreign_customer), {"name": "Tentativa de alteração"}, format="json"
    )
    assert response.status_code == 404
    assert list(Customer.objects.order_by("pk").values()) == before
    assert Customer.objects.filter(pk=own.pk).exists()


def test_delete_cross_tenant_returns_404_and_preserves_database(
    tenant_client, membership, foreign_customer
):
    CustomerFactory(organization=membership.organization)
    before = list(Customer.objects.order_by("pk").values())
    response = tenant_client.delete(detail_url(foreign_customer))
    assert response.status_code == 404
    assert list(Customer.objects.order_by("pk").values()) == before
    assert Customer.objects.filter(pk=foreign_customer.pk).exists()


@pytest.mark.parametrize("injected_field", [None, "organization", "organization_id"])
def test_create_uses_current_organization_even_with_mass_assignment_attempt(
    tenant_client, membership, foreign_customer, injected_field
):
    payload = {
        "name": "  Cliente XPTO  ",
        "email": "cliente@example.com",
        "phone": "0011999999999",
    }
    if injected_field:
        payload[injected_field] = foreign_customer.organization_id
    response = tenant_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    assert set(response.json()) == CUSTOMER_FIELDS
    created = Customer.objects.get(pk=response.json()["id"])
    assert created.organization_id == membership.organization_id
    assert created.name == "Cliente XPTO"
    assert created.email == payload["email"]
    assert created.phone == payload["phone"]
    assert (
        Customer.objects.filter(organization=foreign_customer.organization).count() == 1
    )


def test_create_requires_only_name(tenant_client):
    response = tenant_client.post(LIST_URL, {"name": "Cliente"}, format="json")
    assert response.status_code == 201
    assert response.json()["email"] == response.json()["phone"] == ""


@pytest.mark.parametrize(
    "payload, field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "a" * 256}, "name"),
        ({"name": "Cliente", "email": "invalid"}, "email"),
        ({"name": "Cliente", "phone": "1" * 31}, "phone"),
    ],
)
def test_create_rejects_invalid_fields(tenant_client, payload, field):
    response = tenant_client.post(LIST_URL, payload, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert not Customer.objects.exists()


def test_own_customer_can_be_retrieved_updated_and_deleted(
    tenant_client, membership, foreign_customer
):
    customer = CustomerFactory(
        organization=membership.organization, email="old@example.com"
    )
    created_at = customer.created_at
    foreign_before = Customer.objects.values().get(pk=foreign_customer.pk)
    response = tenant_client.get(detail_url(customer))
    assert response.status_code == 200
    assert response.json()["id"] == customer.pk
    assert set(response.json()) == CUSTOMER_FIELDS

    response = tenant_client.patch(
        detail_url(customer),
        {
            "name": "Atualizado",
            "phone": "+55 11 9999-9999",
            "email": "",
            "organization": foreign_customer.organization_id,
            "organization_id": foreign_customer.organization_id,
        },
        format="json",
    )
    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.name == "Atualizado"
    assert customer.email == ""
    assert customer.phone == "+55 11 9999-9999"
    assert customer.organization_id == membership.organization_id
    assert customer.created_at == created_at
    assert customer.updated_at > created_at

    response = tenant_client.delete(detail_url(customer))
    assert response.status_code == 204
    assert not response.content
    assert not Customer.objects.filter(pk=customer.pk).exists()
    assert Customer.objects.values().get(pk=foreign_customer.pk) == foreign_before


def test_patch_rejects_blank_name_without_changing_customer(tenant_client, membership):
    customer = CustomerFactory(organization=membership.organization)
    before = Customer.objects.values().get(pk=customer.pk)
    response = tenant_client.patch(detail_url(customer), {"name": "   "}, format="json")
    assert response.status_code == 400
    assert Customer.objects.values().get(pk=customer.pk) == before


@pytest.mark.parametrize(
    "method, detail",
    [("get", False), ("post", False), ("get", True), ("patch", True), ("delete", True)],
)
def test_authenticated_user_without_context_is_denied(
    authenticated_client, membership, method, detail
):
    customer = CustomerFactory(organization=membership.organization)
    before = Customer.objects.values().get(pk=customer.pk)
    url = detail_url(customer) if detail else LIST_URL
    response = getattr(authenticated_client, method)(
        url, {"name": "Cliente"}, format="json"
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Selecione uma organização ativa."}
    assert "current_organization_id" not in authenticated_client.session
    assert Customer.objects.values().get(pk=customer.pk) == before


@pytest.mark.parametrize(
    "method, detail",
    [("get", False), ("post", False), ("get", True), ("patch", True), ("delete", True)],
)
def test_anonymous_user_is_denied(api_client, foreign_customer, method, detail):
    url = detail_url(foreign_customer) if detail else LIST_URL
    response = getattr(api_client, method)(url, {"name": "Cliente"}, format="json")
    assert response.status_code == 403


def test_switching_organization_changes_all_customer_access(
    tenant_client, user, membership
):
    first = CustomerFactory(organization=membership.organization)
    second_membership = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = CustomerFactory(organization=second_membership.organization)
    assert tenant_client.get(LIST_URL).json()["results"][0]["id"] == first.pk

    assert (
        tenant_client.put(
            CURRENT_URL,
            {"organization_id": second_membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert [item["id"] for item in tenant_client.get(LIST_URL).json()["results"]] == [
        second.pk
    ]
    assert tenant_client.get(detail_url(first)).status_code == 404
    assert tenant_client.get(detail_url(second)).status_code == 200
    response = tenant_client.post(LIST_URL, {"name": "Novo cliente B"}, format="json")
    assert response.status_code == 201
    assert (
        Customer.objects.get(pk=response.json()["id"]).organization_id
        == second_membership.organization_id
    )


@pytest.mark.parametrize("revocation", ["deactivate", "delete"])
def test_revoked_membership_stops_customer_access(
    tenant_client, membership, revocation
):
    customer = CustomerFactory(organization=membership.organization)
    if revocation == "deactivate":
        membership.is_active = False
        membership.save(update_fields=["is_active"])
    else:
        membership.delete()

    assert tenant_client.get(LIST_URL).status_code == 403
    assert tenant_client.get(detail_url(customer)).status_code == 403
    assert (
        tenant_client.post(LIST_URL, {"name": "Negado"}, format="json").status_code
        == 403
    )
    assert "current_organization_id" not in tenant_client.session
    assert Customer.objects.filter(pk=customer.pk).exists()


def test_superuser_has_no_context_or_cross_tenant_bypass(
    authenticated_client, user, membership, foreign_customer
):
    user.is_staff = user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    assert authenticated_client.get(LIST_URL).status_code == 403
    assert (
        authenticated_client.put(
            CURRENT_URL, {"organization_id": membership.organization_id}, format="json"
        ).status_code
        == 200
    )
    assert authenticated_client.get(LIST_URL).json()["count"] == 0
    assert authenticated_client.get(detail_url(foreign_customer)).status_code == 404


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_owner_and_admin_can_use_customer_crud(tenant_client, membership, role):
    membership.role = role
    membership.save(update_fields=["role"])
    created = tenant_client.post(LIST_URL, {"name": "Cliente"}, format="json")
    assert created.status_code == 201
    url = f"{LIST_URL}{created.json()['id']}/"
    assert tenant_client.get(LIST_URL).status_code == 200
    assert tenant_client.get(url).status_code == 200
    assert (
        tenant_client.patch(url, {"name": "Alterado"}, format="json").status_code == 200
    )
    assert tenant_client.delete(url).status_code == 204


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_writes_without_csrf_are_rejected(tenant_client, membership, method):
    customer = CustomerFactory(organization=membership.organization)
    before = list(Customer.objects.values())
    tenant_client.credentials()
    url = LIST_URL if method == "post" else detail_url(customer)
    response = getattr(tenant_client, method)(url, {"name": "Tentativa"}, format="json")
    assert response.status_code == 403
    assert list(Customer.objects.values()) == before


def test_pagination_has_fixed_size_stable_order_and_tenant_only_count(
    tenant_client, membership, foreign_customer
):
    customers = CustomerFactory.create_batch(
        26, organization=membership.organization, name="Mesmo nome"
    )
    expected = [customer.pk for customer in customers]
    first = tenant_client.get(LIST_URL, {"page_size": 1000000})
    second = tenant_client.get(LIST_URL, {"page": 2})

    assert first.status_code == second.status_code == 200
    assert first.json()["count"] == second.json()["count"] == 26
    assert [item["id"] for item in first.json()["results"]] == expected[:25]
    assert [item["id"] for item in second.json()["results"]] == expected[25:]
    assert first.json()["next"] and second.json()["previous"]
    assert second.json()["next"] is None
    assert isinstance(tenant_client.get("/api/v1/organizations/").json(), list)


def test_put_is_not_exposed_but_head_and_options_work(tenant_client, membership):
    customer = CustomerFactory(organization=membership.organization)
    assert (
        tenant_client.put(
            detail_url(customer), {"name": "Negado"}, format="json"
        ).status_code
        == 405
    )
    assert tenant_client.head(detail_url(customer)).status_code == 200
    response = tenant_client.options(detail_url(customer))
    assert response.status_code == 200
    assert "PUT" not in response["Allow"]
