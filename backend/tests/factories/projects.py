import factory

from apps.projects.models import Project, ProjectStage

from .organizations import OrganizationFactory


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    organization = factory.SubFactory(OrganizationFactory)
    customer = None
    name = factory.Sequence(lambda number: f"Project {number}")


class ProjectStageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectStage

    project = factory.SubFactory(ProjectFactory)
    parent = None
    position = 0
    name = factory.Sequence(lambda number: f"Stage {number}")
