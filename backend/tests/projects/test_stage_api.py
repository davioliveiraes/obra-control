import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from apps.projects.models import Project, ProjectStage
from tests.factories.organizations import MembershipFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
FIELDS = {
    "id",
    "name",
    "description",
    "parent_id",
    "position",
    "created_at",
    "updated_at",
}


def listing(project):
    return f"/api/v1/projects/{project.pk}/stages/"


def detail(stage):
    return f"/api/v1/projects/{stage.project_id}/stages/{stage.pk}/"


@pytest.fixture
def project(membership):
    return ProjectFactory(organization=membership.organization)


def test_flat_complete_listing_order_and_scoping(tenant_client, project):
    root = ProjectStageFactory(project=project, position=3)
    child = ProjectStageFactory(project=project, parent=root, position=1)
    siblings = ProjectStageFactory.create_batch(
        26, project=project, parent=child, position=1
    )
    ProjectStageFactory(project=ProjectFactory(organization=project.organization))
    ProjectStageFactory()
    response = tenant_client.get(listing(project), {"page_size": 1, "page": 2})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert [item["id"] for item in response.json()] == [
        child.pk,
        *[s.pk for s in siblings],
        root.pk,
    ]
    assert all(set(item) == FIELDS for item in response.json())
    assert response.json()[0]["parent_id"] == root.pk
    assert "no-store" in response["Cache-Control"]


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_root_child_patch_detach_and_leaf_delete(
    tenant_client, membership, project, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    response = tenant_client.post(
        listing(project), {"name": "  Fundação  "}, format="json"
    )
    assert response.status_code == 201
    root = ProjectStage.objects.get(pk=response.json()["id"])
    assert root.project == project
    assert root.name == "Fundação"
    assert root.parent_id is None
    assert response.json()["description"] == ""
    assert response.json()["position"] == 0
    response = tenant_client.post(
        listing(project), {"name": "Escavação", "parent_id": root.pk}, format="json"
    )
    assert response.status_code == 201
    child = ProjectStage.objects.get(pk=response.json()["id"])
    assert child.parent_id == root.pk
    assert tenant_client.get(detail(child)).status_code == 200
    response = tenant_client.patch(
        detail(child),
        {"name": "Atualizada", "description": "Texto", "position": 4},
        format="json",
    )
    assert response.status_code == 200
    child.refresh_from_db()
    assert child.parent_id == root.pk
    assert (
        child.position == 4
        and child.description == "Texto"
        and child.name == "Atualizada"
    )
    assert child.updated_at > child.created_at
    assert (
        tenant_client.patch(
            detail(child), {"parent_id": None}, format="json"
        ).status_code
        == 200
    )
    child.refresh_from_db()
    assert child.parent_id is None
    assert (
        tenant_client.patch(
            detail(child), {"parent_id": root.pk}, format="json"
        ).status_code
        == 200
    )
    assert tenant_client.delete(detail(child)).status_code == 204
    assert not ProjectStage.objects.filter(pk=child.pk).exists()
    assert tenant_client.delete(detail(root)).status_code == 204
    assert (
        tenant_client.put(
            listing(project), {"name": "Não permitido"}, format="json"
        ).status_code
        == 405
    )


@pytest.mark.parametrize(
    "field", ["project", "project_id", "organization", "organization_id"]
)
def test_payload_cannot_choose_or_transfer_project(tenant_client, project, field):
    other = ProjectFactory()
    payload = {
        "name": "Etapa",
        field: other.pk if field.startswith("project") else other.organization_id,
    }
    response = tenant_client.post(listing(project), payload, format="json")
    assert response.status_code == 201
    stage = ProjectStage.objects.get(pk=response.json()["id"])
    assert stage.project == project
    assert set(response.json()) == FIELDS
    assert tenant_client.patch(detail(stage), payload, format="json").status_code == 200
    stage.refresh_from_db()
    assert stage.project_id == project.pk


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "a" * 256}, "name"),
        ({"name": "Etapa", "position": -1}, "position"),
        ({"name": "Etapa", "position": 1.5}, "position"),
    ],
)
def test_create_validates_fields(tenant_client, project, payload, field):
    response = tenant_client.post(listing(project), payload, format="json")
    assert response.status_code == 400
    assert field in response.json()
    assert not project.stages.exists()


@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_project_of_another_tenant_is_404(tenant_client, project, method):
    foreign = ProjectStageFactory()
    before = list(ProjectStage.objects.values())
    url = listing(foreign.project) if method in ["get", "post"] else detail(foreign)
    response = getattr(tenant_client, method)(url, {"name": "Ataque"}, format="json")
    assert response.status_code == 404
    assert list(ProjectStage.objects.values()) == before
    assert tenant_client.get(detail(foreign)).status_code == 404


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_stage_id_from_other_project_is_404(tenant_client, project, method):
    other = ProjectFactory(organization=project.organization)
    stage = ProjectStageFactory(project=other)
    before = ProjectStage.objects.values().get(pk=stage.pk)
    response = getattr(tenant_client, method)(
        f"{listing(project)}{stage.pk}/", {"name": "Ataque"}, format="json"
    )
    assert response.status_code == 404
    stage.refresh_from_db()
    assert ProjectStage.objects.values().get(pk=stage.pk) == before


@pytest.mark.parametrize("method", ["post", "patch"])
def test_invalid_parent_ids_are_indistinguishable(tenant_client, project, method):
    stage = ProjectStageFactory(project=project)
    other = ProjectStageFactory(
        project=ProjectFactory(organization=project.organization)
    )
    foreign = ProjectStageFactory()
    before = list(ProjectStage.objects.order_by("pk").values())
    url = listing(project) if method == "post" else detail(stage)
    for parent_id in [other.pk, foreign.pk, 9223372036854775807]:
        response = getattr(tenant_client, method)(
            url, {"name": "Negado", "parent_id": parent_id}, format="json"
        )
        assert response.status_code == 400
        assert response.json() == {"parent_id": ["Etapa pai indisponível."]}
    stage.refresh_from_db()
    assert stage.parent_id is None
    assert list(ProjectStage.objects.order_by("pk").values()) == before


def test_self_parent_and_descendant_cycles_are_rejected(tenant_client, project):
    root = ProjectStageFactory(project=project)
    child = ProjectStageFactory(project=project, parent=root)
    leaf = ProjectStageFactory(project=project, parent=child)
    before = list(ProjectStage.objects.order_by("pk").values())
    for parent_id in [root.pk, leaf.pk]:
        response = tenant_client.patch(
            detail(root), {"parent_id": parent_id}, format="json"
        )
        assert response.status_code == 400
        assert "parent_id" in response.json()
    root.refresh_from_db()
    child.refresh_from_db()
    leaf.refresh_from_db()
    assert root.parent_id is None
    assert child.parent_id == root.pk and leaf.parent_id == child.pk
    assert list(ProjectStage.objects.order_by("pk").values()) == before


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_parent_delete_conflicts_but_project_delete_cascades(
    tenant_client, project, membership, role
):
    membership.role = role
    membership.save(update_fields=["role"])
    root = ProjectStageFactory(project=project)
    child = ProjectStageFactory(project=project, parent=root)
    ProjectStageFactory(project=project, parent=child)
    ProjectStageFactory(project=project)
    foreign = ProjectStageFactory()
    response = tenant_client.delete(detail(root))
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A etapa possui subetapas e não pode ser excluída."
    }
    assert project.stages.count() == 4
    response = tenant_client.delete(f"/api/v1/projects/{project.pk}/")
    assert response.status_code == 204
    assert not Project.objects.filter(pk=project.pk).exists()
    assert not ProjectStage.objects.filter(project_id=project.pk).exists()
    assert ProjectStage.objects.get() == foreign


@pytest.mark.parametrize("superuser", [False, True])
def test_member_is_read_only_without_superuser_bypass(
    tenant_client, project, membership, user, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save(update_fields=["is_staff", "is_superuser"])
    membership.role = MembershipRole.MEMBER
    membership.save(update_fields=["role"])
    stage = ProjectStageFactory(project=project)
    before = ProjectStage.objects.values().get(pk=stage.pk)
    for url in [listing(project), detail(stage)]:
        assert tenant_client.get(url).status_code == 200
        assert tenant_client.head(url).status_code == 200
        assert tenant_client.options(url).status_code == 200
    for method in ["post", "patch", "delete"]:
        response = getattr(tenant_client, method)(
            listing(project) if method == "post" else detail(stage),
            {"name": "Negado"},
            format="json",
        )
        assert response.status_code == 403
    stage.refresh_from_db()
    assert ProjectStage.objects.count() == 1
    assert ProjectStage.objects.values().get(pk=stage.pk) == before


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_writes_require_real_csrf(tenant_client, project, method):
    stage = ProjectStageFactory(project=project)
    tenant_client.credentials()
    response = getattr(tenant_client, method)(
        listing(project) if method == "post" else detail(stage),
        {"name": "Negado"},
        format="json",
    )
    assert response.status_code == 403
    stage.refresh_from_db()
    assert ProjectStage.objects.count() == 1


def test_anonymous_missing_context_and_revoked_membership_are_denied(
    authenticated_client, project, membership
):
    stage = ProjectStageFactory(project=project)
    anonymous = APIClient(enforce_csrf_checks=True)
    assert anonymous.get(listing(project)).status_code == 403
    assert authenticated_client.get(listing(project)).status_code == 403
    assert (
        authenticated_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    membership.is_active = False
    membership.save(update_fields=["is_active"])
    assert authenticated_client.get(detail(stage)).status_code == 403
    assert "current_organization_id" not in authenticated_client.session


def test_switching_organization_changes_stage_access(tenant_client, project, user):
    first = ProjectStageFactory(project=project)
    other = MembershipFactory(user=user, role=MembershipRole.OWNER)
    second = ProjectStageFactory(
        project=ProjectFactory(organization=other.organization)
    )
    assert tenant_client.get(detail(first)).status_code == 200
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": other.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(detail(first)).status_code == 404
    assert tenant_client.get(detail(second)).status_code == 200
    assert (
        tenant_client.post(
            listing(second.project), {"name": "Nova etapa B"}, format="json"
        ).status_code
        == 201
    )
