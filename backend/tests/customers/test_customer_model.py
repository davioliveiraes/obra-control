import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.customers.models import Customer
from tests.factories.customers import CustomerFactory
from tests.factories.organizations import OrganizationFactory


@pytest.mark.django_db
def test_customer_is_created_with_required_organization_and_timestamps():
    before = timezone.now()
    customer = CustomerFactory()
    customer.refresh_from_db()

    assert customer.organization.customers.get() == customer
    assert customer.email == customer.phone == ""
    assert before <= customer.created_at <= customer.updated_at <= timezone.now()
    assert timezone.is_aware(customer.created_at)
    assert not customer.organization.memberships.exists()


@pytest.mark.django_db
def test_database_rejects_customer_without_organization():
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Customer.objects.create(name="Cliente sem organização")
    assert error.value.__cause__.diag.column_name == "organization_id"


@pytest.mark.django_db
def test_database_enforces_organization_foreign_key():
    organization = OrganizationFactory()
    missing_id = organization.pk
    organization.delete()
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        Customer.objects.create(name="Cliente", organization_id=missing_id)
        connection.check_constraints()
    assert error.value.__cause__.sqlstate == "23503"


@pytest.mark.parametrize("name", ["", None])
def test_model_validation_requires_name(name):
    with pytest.raises(ValidationError) as error:
        Customer(name=name).full_clean(exclude=["organization"])
    assert "name" in error.value.message_dict


@pytest.mark.django_db
def test_name_and_email_can_repeat_within_and_between_organizations():
    first = CustomerFactory(name="Cliente", email="cliente@example.com")
    second = CustomerFactory(
        organization=first.organization, name=first.name, email=first.email
    )
    third = CustomerFactory(name=first.name, email=first.email)

    assert len({first.pk, second.pk, third.pk}) == 3
    assert first.organization_id != third.organization_id
    assert Customer.objects.filter(name=first.name, email=first.email).count() == 3


@pytest.mark.django_db
def test_deleting_organization_cascades_only_to_its_customers():
    owned = CustomerFactory()
    other = CustomerFactory()
    owned.organization.delete()
    assert not Customer.objects.filter(pk=owned.pk).exists()
    assert Customer.objects.filter(pk=other.pk).exists()
