import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.models import Membership, MembershipRole, Organization
from tests.factories.accounts import UserFactory
from tests.factories.organizations import MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db


def test_membership_links_custom_user_and_organization_with_defaults():
    before = timezone.now()
    membership = MembershipFactory()
    membership.refresh_from_db()

    assert type(membership.user) is get_user_model()
    assert membership.user._meta.label == "accounts.User"
    assert membership.user.memberships.get() == membership
    assert membership.organization.memberships.get() == membership
    assert membership.role == MembershipRole.MEMBER
    assert membership.is_active is True
    assert before <= membership.created_at <= membership.updated_at <= timezone.now()


@pytest.mark.parametrize("role", [MembershipRole.OWNER, MembershipRole.ADMIN])
def test_membership_can_store_explicit_role_without_django_privileges(role):
    membership = MembershipFactory(role=role)
    membership.refresh_from_db()

    assert membership.role == role
    assert membership.user.is_staff is False
    assert membership.user.is_superuser is False


def test_model_validation_rejects_unknown_role():
    membership = MembershipFactory.build(role="engineer")
    with pytest.raises(ValidationError) as error:
        membership.full_clean(
            exclude=["user", "organization"], validate_constraints=False
        )
    assert "role" in error.value.message_dict


def test_user_can_belong_to_different_organizations():
    user = UserFactory()
    first = MembershipFactory(user=user)
    second = MembershipFactory(user=user)

    assert first.organization_id != second.organization_id
    assert set(user.memberships.values_list("organization_id", flat=True)) == {
        first.organization_id,
        second.organization_id,
    }


def test_organization_can_have_different_users():
    organization = OrganizationFactory()
    first = MembershipFactory(organization=organization)
    second = MembershipFactory(organization=organization)

    assert first.user_id != second.user_id
    assert set(organization.memberships.values_list("user_id", flat=True)) == {
        first.user_id,
        second.user_id,
    }


@pytest.mark.parametrize("is_active", [True, False])
def test_database_rejects_duplicate_membership_even_if_existing_is_inactive(is_active):
    existing = MembershipFactory(is_active=is_active)

    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Membership.objects.create(
            organization=existing.organization, user=existing.user
        )

    assert (
        error.value.__cause__.diag.constraint_name
        == "organizations_membership_org_user_unique"
    )
    assert (
        Membership.objects.filter(
            organization=existing.organization, user=existing.user
        ).count()
        == 1
    )


def test_membership_can_be_deactivated_without_removing_the_relationship():
    membership = MembershipFactory()
    created_at = membership.created_at
    updated_at = membership.updated_at
    membership.is_active = False
    membership.save()
    membership.refresh_from_db()

    assert membership.is_active is False
    assert membership.created_at == created_at
    assert membership.updated_at > updated_at
    assert membership.user.memberships.get() == membership
    assert membership.organization.memberships.get() == membership


@pytest.mark.parametrize("deleted_entity", ["user", "organization"])
def test_deleting_either_entity_removes_only_the_association_and_deleted_entity(
    deleted_entity,
):
    membership = MembershipFactory()
    user_id = membership.user_id
    organization_id = membership.organization_id
    getattr(membership, deleted_entity).delete()

    assert not Membership.objects.filter(pk=membership.pk).exists()
    if deleted_entity == "organization":
        assert get_user_model().objects.filter(pk=user_id).exists()
    else:
        assert Organization.objects.filter(pk=organization_id).exists()
