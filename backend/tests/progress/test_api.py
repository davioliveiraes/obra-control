from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.organizations.models import MembershipRole
from apps.progress.models import StageProgressEntry
from tests.factories.organizations import MembershipFactory
from tests.factories.progress import StageProgressEntryFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db
FIELDS = {
    "id",
    "progress_date",
    "progress_percentage",
    "notes",
    "created_at",
    "updated_at",
}


def listing(stage):
    return f"/api/v1/projects/{stage.project_id}/stages/{stage.pk}/progress/"


def detail(entry):
    return f"{listing(entry.stage)}{entry.pk}/"


def payload(**overrides):
    return {"progress_date": "2026-09-09", "progress_percentage": "62.50", **overrides}


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_crud_with_stage_only_from_url(tenant_client, stage, membership, role):
    membership.role = role
    membership.save()
    other = ProjectStageFactory()
    context_attack = {
        "stage": other.pk,
        "stage_id": other.pk,
        "project": other.project_id,
        "project_id": other.project_id,
        "organization": other.project.organization_id,
        "organization_id": other.project.organization_id,
    }
    response = tenant_client.post(
        listing(stage), payload(**context_attack), format="json"
    )
    assert response.status_code == 201 and set(response.json()) == FIELDS
    entry = StageProgressEntry.objects.get()
    assert entry.stage == stage and entry.notes == ""
    assert isinstance(entry.progress_percentage, Decimal)
    assert entry.progress_percentage == Decimal("62.50")
    assert tenant_client.get(detail(entry)).json() == response.json()
    assert tenant_client.get(listing(stage)).json()["results"] == [response.json()]
    response = tenant_client.patch(
        detail(entry),
        payload(
            progress_date="2026-09-10",
            progress_percentage="60.25",
            notes="Revisado",
            **context_attack,
        ),
        format="json",
    )
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.stage == stage and entry.progress_date == date(2026, 9, 10)
    assert entry.progress_percentage == Decimal("60.25") and entry.notes == "Revisado"
    assert tenant_client.put(detail(entry), payload(), format="json").status_code == 405
    assert tenant_client.delete(detail(entry)).status_code == 204
    assert not StageProgressEntry.objects.filter(pk=entry.pk).exists()
    stage.refresh_from_db()
    stage.project.refresh_from_db()


def test_history_allows_retroactive_future_and_decreasing_percentages(
    tenant_client, stage
):
    for day, percentage in [("2000-01-01", "70.00"), ("2100-01-01", "68.00")]:
        response = tenant_client.post(
            listing(stage),
            payload(progress_date=day, progress_percentage=percentage),
            format="json",
        )
        assert response.status_code == 201
    entries = list(stage.progress_entries.order_by("progress_date"))
    assert [entry.progress_percentage for entry in entries] == [
        Decimal("70.00"),
        Decimal("68.00"),
    ]
    assert len(entries) == 2


def test_fixed_pagination_order_and_stage_scoping(tenant_client, stage):
    entries = [
        StageProgressEntryFactory(
            stage=stage, progress_date=date(2026, 1, 1) + timedelta(days=i)
        )
        for i in range(27)
    ]
    StageProgressEntryFactory(stage=ProjectStageFactory(project=stage.project))
    StageProgressEntryFactory()
    response = tenant_client.get(
        listing(stage),
        {"page_size": 10000, "ordering": "progress_date", "latest": True},
    )
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    first = response.json()
    second = tenant_client.get(listing(stage), {"page": 2}).json()
    assert first["count"] == 27 and len(first["results"]) == 25
    assert [item["id"] for item in first["results"] + second["results"]] == [
        entry.pk for entry in reversed(entries)
    ]


@pytest.mark.parametrize(
    "percentage", ["0.00", "0.01", "33.33", "62.50", "99.99", "100.00"]
)
def test_decimal_precision_and_inclusive_limits(tenant_client, stage, percentage):
    response = tenant_client.post(
        listing(stage), payload(progress_percentage=percentage), format="json"
    )
    assert response.status_code == 201
    assert response.json()["progress_percentage"] == percentage
    entry = StageProgressEntry.objects.get()
    entry.refresh_from_db()
    assert isinstance(entry.progress_percentage, Decimal)
    assert entry.progress_percentage == Decimal(percentage)


@pytest.mark.parametrize(
    "percentage",
    ["-0.01", "100.01", "150.00", "1000.00", "1.001", "NaN", "Infinity", "-Infinity"],
)
def test_invalid_decimal_create_and_patch_never_mutate(
    tenant_client, entry, percentage
):
    before = StageProgressEntry.objects.values().get(pk=entry.pk)
    for method, url in [("post", listing(entry.stage)), ("patch", detail(entry))]:
        response = getattr(tenant_client, method)(
            url,
            payload(progress_date="2026-09-10", progress_percentage=percentage),
            format="json",
        )
        assert response.status_code == 400 and "progress_percentage" in response.json()
        entry.refresh_from_db()
        assert StageProgressEntry.objects.count() == 1
        assert StageProgressEntry.objects.values().get(pk=entry.pk) == before


@pytest.mark.parametrize(
    "data,field",
    [
        ({"progress_percentage": "25.00"}, "progress_date"),
        ({"progress_date": "2026-09-09"}, "progress_percentage"),
        (payload(progress_date=None), "progress_date"),
        (payload(progress_percentage=None), "progress_percentage"),
        (payload(progress_date="2026-02-30"), "progress_date"),
    ],
)
def test_required_and_invalid_fields(tenant_client, stage, data, field):
    response = tenant_client.post(listing(stage), data, format="json")
    assert response.status_code == 400 and field in response.json()
    assert not StageProgressEntry.objects.exists()


def test_duplicate_date_in_create_and_patch_preserves_history(tenant_client, entry):
    other = StageProgressEntryFactory(
        stage=entry.stage, progress_date=date(2026, 9, 10)
    )
    before = list(StageProgressEntry.objects.order_by("pk").values())
    for method, url in [("post", listing(entry.stage)), ("patch", detail(other))]:
        response = getattr(tenant_client, method)(
            url, payload(notes="Não salvar"), format="json"
        )
        assert response.status_code == 400
        assert response.json() == {
            "progress_date": [
                "Já existe um registro de progresso para esta etapa nesta data."
            ]
        }
        assert list(StageProgressEntry.objects.order_by("pk").values()) == before
    assert (
        tenant_client.patch(
            detail(entry),
            {"progress_date": entry.progress_date.isoformat()},
            format="json",
        ).status_code
        == 200
    )
    assert (
        tenant_client.patch(
            detail(entry), {"notes": "Somente observação"}, format="json"
        ).status_code
        == 200
    )
    entry.refresh_from_db()
    assert entry.progress_percentage == Decimal("25.00")


@pytest.mark.parametrize("scope", ["stage", "project", "tenant"])
def test_nested_scoping_blocks_foreign_resources_without_mutation(
    tenant_client, stage, scope
):
    if scope == "stage":
        other_stage = ProjectStageFactory(project=stage.project)
    elif scope == "project":
        other_stage = ProjectStageFactory(
            project=ProjectFactory(organization=stage.project.organization)
        )
    else:
        other_stage = ProjectStageFactory()
    external = StageProgressEntryFactory(stage=other_stage)
    before = StageProgressEntry.objects.values().get(pk=external.pk)
    for method in ["get", "patch", "delete"]:
        response = getattr(tenant_client, method)(
            f"{listing(stage)}{external.pk}/", payload(notes="Negado"), format="json"
        )
        assert response.status_code == 404
    if scope != "stage":
        wrong_collection = (
            f"/api/v1/projects/{stage.project_id}/stages/{other_stage.pk}/progress/"
        )
        for method, url in [
            ("get", wrong_collection),
            ("post", wrong_collection),
            ("get", f"{wrong_collection}{external.pk}/"),
            ("patch", f"{wrong_collection}{external.pk}/"),
            ("delete", f"{wrong_collection}{external.pk}/"),
        ]:
            assert (
                getattr(tenant_client, method)(
                    url, payload(), format="json"
                ).status_code
                == 404
            )
    if scope == "tenant":
        for method, url in [
            ("get", listing(other_stage)),
            ("post", listing(other_stage)),
            ("get", detail(external)),
            ("patch", detail(external)),
            ("delete", detail(external)),
        ]:
            assert (
                getattr(tenant_client, method)(
                    url, payload(), format="json"
                ).status_code
                == 404
            )
    external.refresh_from_db()
    assert StageProgressEntry.objects.count() == 1
    assert StageProgressEntry.objects.values().get(pk=external.pk) == before


@pytest.mark.parametrize("superuser", [False, True])
def test_member_is_read_only_even_for_superuser(
    tenant_client, entry, membership, user, superuser
):
    user.is_staff = user.is_superuser = superuser
    user.save()
    membership.role = MembershipRole.MEMBER
    membership.save()
    before = StageProgressEntry.objects.values().get(pk=entry.pk)
    for url in [listing(entry.stage), detail(entry)]:
        for method in ["get", "head", "options"]:
            assert getattr(tenant_client, method)(url).status_code == 200
    for method, url in [
        ("post", listing(entry.stage)),
        ("patch", detail(entry)),
        ("delete", detail(entry)),
    ]:
        assert (
            getattr(tenant_client, method)(
                url, payload(progress_date="2026-09-10"), format="json"
            ).status_code
            == 403
        )
    assert StageProgressEntry.objects.count() == 1
    entry.refresh_from_db()
    assert StageProgressEntry.objects.values().get(pk=entry.pk) == before
    foreign = StageProgressEntryFactory()
    assert tenant_client.get(detail(foreign)).status_code == 404
    membership.delete()
    assert tenant_client.get(detail(entry)).status_code == 403


def test_csrf_protects_all_writes(tenant_client, entry):
    before = StageProgressEntry.objects.values().get(pk=entry.pk)
    tenant_client.credentials()
    assert tenant_client.get(listing(entry.stage)).status_code == 200
    for method, url in [
        ("post", listing(entry.stage)),
        ("patch", detail(entry)),
        ("delete", detail(entry)),
    ]:
        response = getattr(tenant_client, method)(
            url, payload(progress_date="2026-09-10"), format="json"
        )
        assert response.status_code == 403 and "CSRF" in response.json()["detail"]
    assert StageProgressEntry.objects.count() == 1
    entry.refresh_from_db()
    assert StageProgressEntry.objects.values().get(pk=entry.pk) == before


def test_revocation_denies_next_request(tenant_client, entry, membership):
    assert tenant_client.get(detail(entry)).status_code == 200
    membership.is_active = False
    membership.save()
    assert tenant_client.get(listing(entry.stage)).status_code == 403
    assert tenant_client.get(detail(entry)).status_code == 403


def test_anonymous_and_missing_context_are_denied(authenticated_client, entry):
    anonymous = APIClient(enforce_csrf_checks=True)
    for client in [anonymous, authenticated_client]:
        for url in [listing(entry.stage), detail(entry)]:
            assert client.get(url).status_code == 403


def test_tenant_switch_changes_visible_history_and_effective_role(
    tenant_client, entry, user
):
    membership = MembershipFactory(user=user, role=MembershipRole.MEMBER)
    other = StageProgressEntryFactory(
        stage=ProjectStageFactory(
            project=ProjectFactory(organization=membership.organization)
        )
    )
    assert tenant_client.get(detail(entry)).status_code == 200
    assert tenant_client.get(detail(other)).status_code == 404
    assert (
        tenant_client.put(
            "/api/v1/organizations/current/",
            {"organization_id": membership.organization_id},
            format="json",
        ).status_code
        == 200
    )
    assert tenant_client.get(detail(entry)).status_code == 404
    assert tenant_client.get(detail(other)).status_code == 200
    assert (
        tenant_client.patch(
            detail(other), {"notes": "Negado"}, format="json"
        ).status_code
        == 403
    )
