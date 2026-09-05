import factory

from apps.organizations.models import Membership, Organization

from .accounts import UserFactory


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda number: f"Organization {number}")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    organization = factory.SubFactory(OrganizationFactory)
    user = factory.SubFactory(UserFactory)
