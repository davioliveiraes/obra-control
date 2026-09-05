import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from apps.projects.models import Project, ProjectStatus
from tests.factories.customers import CustomerFactory
from tests.factories.organizations import MembershipFactory
from tests.factories.projects import ProjectFactory

pytestmark = pytest.mark.django_db
LIST_URL = "/api/v1/projects/"
CURRENT_URL = "/api/v1/organizations/current/"
PROJECT_FIELDS = {
    "id",
    "name",
    "customer_id",
    "status",
    "description",
    "planned_start_date",
    "planned_end_date",
    "created_at",
    "updated_at",
}


def detail_url(project):
    return f"{LIST_URL}{project.pk}/"


def test_list_isolates_items_and_count(tenant_client, membership, foreign_project):
    first = ProjectFactory(organization=membership.organization, name="Obra A1")
    second = ProjectFactory(organization=membership.organization, name="Obra A2")
    response = tenant_client.get(LIST_URL)
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [p["id"] for p in response.json()["results"]] == [first.pk, second.pk]
    assert foreign_project.name not in response.content.decode()
    assert all(set(p) == PROJECT_FIELDS for p in response.json()["results"])
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_cross_tenant_project_is_404_and_database_is_unchanged(
    tenant_client, membership, foreign_project, method
):
    ProjectFactory(organization=membership.organization)
    before = list(Project.objects.order_by("pk").values())
    response = getattr(tenant_client, method)(
        detail_url(foreign_project), {"name": "Ataque"}, format="json"
    )
    missing = getattr(tenant_client, method)(
        f"{LIST_URL}9223372036854775807/", {"name": "Ataque"}, format="json"
    )
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json()
    foreign_project.refresh_from_db()
    assert foreign_project.name == "Obra confidencial B"
    assert list(Project.objects.order_by("pk").values()) == before


@pytest.mark.parametrize(
    "injected_field", [None, "organization", "organization_id", "tenant", "tenant_id"]
)
def test_create_uses_context_and_ignores_tenant_payload(
    tenant_client, membership, foreign_project, injected_field
):
    payload = {"name": "  Obra interna  "}
    if injected_field:
        payload[injected_field] = foreign_project.organization_id
    response = tenant_client.post(LIST_URL, payload, format="json")
    assert response.status_code == 201
    assert set(response.json()) == PROJECT_FIELDS
    project = Project.objects.get(pk=response.json()["id"])
    assert project.organization_id == membership.organization_id
    assert project.name == "Obra interna"
    assert project.status == ProjectStatus.PLANNING
    assert project.customer_id is None
    assert response.json()["customer_id"] is None
    assert project.description == ""
    assert project.planned_start_date is project.planned_end_date is None


def test_create_with_customer_and_full_payload(tenant_client, membership):
    customer = CustomerFactory(organization=membership.organization)
    payload = {
        "name": "Residencial Aurora",
        "customer_id": customer.pk,
        "status": "active",
        "description": "Construção residencial",
        "planned_start_date": "2026-10-01",
        "planned_end_date": "2027-08-30",
    }
    response = tenant_client.post(LIST_URL, payload, format="json")
    assert response.status_code == 201
    project = Project.objects.get(pk=response.json()["id"])
    assert project.customer_id == customer.pk
    assert project.organization_id == customer.organization_id
    assert all(response.json()[key] == value for key, value in payload.items())


@pytest.mark.parametrize("method", ["post", "patch"])
def test_foreign_customer_and_missing_customer_have_same_error_and_do_not_write(
    tenant_client, membership, foreign_project, method
):
    customer = CustomerFactory(organization=foreign_project.organization)
    own_customer = CustomerFactory(organization=membership.organization)
    project = ProjectFactory(
        organization=membership.organization, customer=own_customer
    )
    before = list(Project.objects.order_by("pk").values())
    url = LIST_URL if method == "post" else detail_url(project)
    response = getattr(tenant_client, method)(
        url, {"name": "Ataque", "customer_id": customer.pk}, format="json"
    )
    missing = getattr(tenant_client, method)(
        url, {"name": "Ataque", "customer_id": 9223372036854775807}, format="json"
    )
    assert response.status_code == missing.status_code == 400
    assert (
        response.json() == missing.json() == {"customer_id": ["Cliente indisponível."]}
    )
    project.refresh_from_db()
    assert project.customer_id == own_customer.pk
    assert list(Project.objects.order_by("pk").values()) == before


def test_patch_can_assign_replace_and_remove_customer(tenant_client, membership):
    project = ProjectFactory(organization=membership.organization)
    first = CustomerFactory(organization=membership.organization)
    second = CustomerFactory(organization=membership.organization)
    for customer_id in [first.pk, second.pk, None]:
        response = tenant_client.patch(
            detail_url(project), {"customer_id": customer_id}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["customer_id"] == customer_id
        project.refresh_from_db()
        assert project.customer_id == customer_id


def test_own_crud_and_customer_deletion_preserve_project(
    tenant_client, membership, foreign_project
):
    customer = CustomerFactory(organization=membership.organization)
    project = ProjectFactory(organization=membership.organization, customer=customer)
    response = tenant_client.get(detail_url(project))
    assert response.status_code == 200
    assert set(response.json()) == PROJECT_FIELDS
    response = tenant_client.patch(
        detail_url(project),
        {
            "name": "Atualizada",
            "description": "Descrição",
            "status": "completed",
            "organization": foreign_project.organization_id,
            "organization_id": foreign_project.organization_id,
        },
        format="json",
    )
    assert response.status_code == 200
    project.refresh_from_db()
    assert project.name == "Atualizada"
    assert project.description == "Descrição"
    assert project.status == "completed"
    assert project.organization_id == membership.organization_id
    assert project.updated_at > project.created_at
    assert tenant_client.delete(f"/api/v1/customers/{customer.pk}/").status_code == 204
    project.refresh_from_db()
    assert project.customer_id is None
    response = tenant_client.get(detail_url(project))
    assert response.status_code == 200
    assert response.json()["customer_id"] is None
    assert tenant_client.delete(detail_url(project)).status_code == 204
    assert not Project.objects.filter(pk=project.pk).exists()
    assert Project.objects.filter(pk=foreign_project.pk).exists()


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "a" * 256}, "name"),
        ({"name": "Obra", "status": "invalid"}, "status"),
        ({"name": "Obra", "planned_start_date": "bad-date"}, "planned_start_date"),
        ({"name": "Obra", "customer_id": 2**63}, "customer_id"),
    ],
)
def test_create_rejects_invalid_payload(tenant_client, payload, field):
    response = tenant_client.post(LIST_URL, payload, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert not Project.objects.exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"status": "unknown"},
        {"planned_start_date": "2026-11-01"},
        {"planned_end_date": "2026-09-01"},
    ],
)
def test_patch_validates_fields_and_dates_against_persisted_values(
    tenant_client, membership, payload
):
    project = ProjectFactory(
        organization=membership.organization,
        planned_start_date="2026-10-01",
        planned_end_date="2026-10-10",
    )
    before = Project.objects.values().get(pk=project.pk)
    response = tenant_client.patch(detail_url(project), payload, format="json")
    assert response.status_code == 400
    assert Project.objects.values().get(pk=project.pk) == before


def test_api_rejects_reversed_dates_before_database_write(tenant_client):
    response = tenant_client.post(
        LIST_URL,
        {
            "name": "Inválida",
            "planned_start_date": "2026-10-10",
            "planned_end_date": "2026-10-01",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "planned_end_date" in response.json()
    assert not Project.objects.exists()


@pytest.mark.parametrize(
    "start,end",
    [
        (None, None),
        ("2026-10-01", None),
        (None, "2026-10-01"),
        ("2026-10-01", "2026-10-01"),
    ],
)
def test_api_accepts_optional_and_equal_dates(tenant_client, start, end):
    response = tenant_client.post(
        LIST_URL,
        {
            "name": "Obra",
            "customer_id": None,
            "planned_start_date": start,
            "planned_end_date": end,
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["planned_start_date"] == start
    assert response.json()["planned_end_date"] == end


def test_patch_can_clear_dates_or_move_both_together(tenant_client, membership):
    project = ProjectFactory(
        organization=membership.organization,
        status=ProjectStatus.ACTIVE,
        planned_start_date="2026-10-01",
        planned_end_date="2026-10-10",
    )
    for payload in [
        {"planned_start_date": "2026-11-01", "planned_end_date": "2026-11-10"},
        {"planned_start_date": None},
        {"planned_end_date": None},
        {"name": "Renomeada"},
    ]:
        response = tenant_client.patch(detail_url(project), payload, format="json")
        assert response.status_code == 200
        assert all(response.json()[key] == value for key, value in payload.items())
    project.refresh_from_db()
    assert project.planned_start_date is project.planned_end_date is None
    assert project.status == ProjectStatus.ACTIVE


@pytest.mark.parametrize(
    "method,detail",
    [
        ("get", False),
        ("post", False),
        ("get", True),
        ("patch", True),
        ("delete", True),
    ],
)
def test_anonymous_and_authenticated_without_context_are_denied(
    authenticated_client, membership, method, detail
):
    project = ProjectFactory(organization=membership.organization)
    url = detail_url(project) if detail else LIST_URL
    # A separate client has no login cookies; authenticated_client has no selected tenant.
    anonymous = APIClient(enforce_csrf_checks=True)
    before = list(Project.objects.values())
    for client in [anonymous, authenticated_client]:
        response = getattr(client, method)(url, {"name": "Ataque"}, format="json")
        assert response.status_code == 403
    assert "current_organization_id" not in authenticated_client.session
    assert list(Project.objects.values()) == before


def test_tenant_switch_changes_list_and_create_customer_scope(
    tenant_client, user, membership
):
    first_customer = CustomerFactory(organization=membership.organization)
    first = ProjectFactory(
        organization=membership.organization, customer=first_customer
    )
    other = MembershipFactory(user=user)
    second_customer = CustomerFactory(organization=other.organization)
    second = ProjectFactory(organization=other.organization)
    assert [p["id"] for p in tenant_client.get(LIST_URL).json()["results"]] == [
        first.pk
    ]
    assert (
        tenant_client.put(
            CURRENT_URL, {"organization_id": other.organization_id}, format="json"
        ).status_code
        == 200
    )
    assert [p["id"] for p in tenant_client.get(LIST_URL).json()["results"]] == [
        second.pk
    ]
    assert tenant_client.get(detail_url(first)).status_code == 404
    assert (
        tenant_client.post(
            LIST_URL,
            {"name": "Inválida", "customer_id": first_customer.pk},
            format="json",
        ).status_code
        == 400
    )
    response = tenant_client.post(
        LIST_URL, {"name": "Obra B", "customer_id": second_customer.pk}, format="json"
    )
    assert response.status_code == 201
    assert (
        Project.objects.get(pk=response.json()["id"]).organization_id
        == other.organization_id
    )


@pytest.mark.parametrize("revocation", ["deactivate", "delete"])
def test_revoked_membership_stops_access(tenant_client, membership, revocation):
    project = ProjectFactory(organization=membership.organization)
    if revocation == "deactivate":
        membership.is_active = False
        membership.save(update_fields=["is_active"])
    else:
        membership.delete()
    assert tenant_client.get(LIST_URL).status_code == 403
    assert tenant_client.get(detail_url(project)).status_code == 403
    assert (
        tenant_client.post(LIST_URL, {"name": "Negada"}, format="json").status_code
        == 403
    )
    assert "current_organization_id" not in tenant_client.session
    assert Project.objects.filter(pk=project.pk).exists()


def test_superuser_has_no_bypass(
    authenticated_client, user, membership, foreign_project
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
    assert authenticated_client.get(detail_url(foreign_project)).status_code == 404


@pytest.mark.parametrize("role", MembershipRole.values)
def test_active_roles_have_same_crud_access(tenant_client, membership, role):
    membership.role = role
    membership.save(update_fields=["role"])
    response = tenant_client.post(LIST_URL, {"name": "Obra"}, format="json")
    assert response.status_code == 201
    url = f"{LIST_URL}{response.json()['id']}/"
    assert tenant_client.get(url).status_code == 200
    for status in ProjectStatus.values:
        assert (
            tenant_client.patch(url, {"status": status}, format="json").status_code
            == 200
        )
    assert tenant_client.delete(url).status_code == 204


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_writes_without_csrf_are_rejected(tenant_client, membership, method):
    project = ProjectFactory(organization=membership.organization)
    before = list(Project.objects.values())
    tenant_client.credentials()
    url = LIST_URL if method == "post" else detail_url(project)
    response = getattr(tenant_client, method)(url, {"name": "Ataque"}, format="json")
    assert response.status_code == 403
    assert list(Project.objects.values()) == before


def test_fixed_pagination_stable_order_and_no_put(
    tenant_client, membership, foreign_project
):
    projects = ProjectFactory.create_batch(
        26, organization=membership.organization, name="Obra"
    )
    first = tenant_client.get(LIST_URL, {"page_size": 1000000})
    second = tenant_client.get(LIST_URL, {"page": 2})
    assert first.status_code == second.status_code == 200
    assert first.json()["count"] == second.json()["count"] == 26
    assert [p["id"] for p in first.json()["results"]] == [p.pk for p in projects[:25]]
    assert [p["id"] for p in second.json()["results"]] == [projects[-1].pk]
    assert first.json()["next"] and second.json()["previous"]
    assert second.json()["next"] is None
    url = detail_url(projects[0])
    assert tenant_client.put(url, {"name": "Negada"}, format="json").status_code == 405
    assert tenant_client.head(url).status_code == 200
    options = tenant_client.options(url)
    assert options.status_code == 200
    assert "PUT" not in options["Allow"]
