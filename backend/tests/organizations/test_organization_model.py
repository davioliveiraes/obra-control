import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.organizations.models import Organization
from tests.factories.organizations import OrganizationFactory


@pytest.mark.django_db
def test_organization_is_created_with_timestamps_and_without_memberships():
    before = timezone.now()
    organization = OrganizationFactory(name="Construtora Exemplo")
    organization.refresh_from_db()

    assert organization.name == "Construtora Exemplo"
    assert (
        before <= organization.created_at <= organization.updated_at <= timezone.now()
    )
    assert timezone.is_aware(organization.created_at)
    assert timezone.is_aware(organization.updated_at)
    assert not organization.memberships.exists()


@pytest.mark.parametrize("name", ["", None])
def test_name_is_required_by_model_validation(name):
    organization = Organization(name=name)
    with pytest.raises(ValidationError) as error:
        organization.full_clean()
    assert "name" in error.value.message_dict


@pytest.mark.django_db
def test_different_organizations_can_have_the_same_name():
    first = OrganizationFactory(name="Construtora Exemplo")
    second = OrganizationFactory(name=first.name)

    assert first.pk != second.pk
    assert Organization.objects.filter(name=first.name).count() == 2
