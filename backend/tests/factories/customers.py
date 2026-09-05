import factory

from apps.customers.models import Customer

from .organizations import OrganizationFactory


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Customer

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda number: f"Customer {number}")
