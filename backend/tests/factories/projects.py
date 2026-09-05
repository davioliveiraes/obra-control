import factory

from apps.projects.models import Project

from .organizations import OrganizationFactory


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    organization = factory.SubFactory(OrganizationFactory)
    customer = None
    name = factory.Sequence(lambda number: f"Project {number}")
