import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError
from django.utils import timezone

from apps.projects.models import ProjectStage
from tests.factories.projects import ProjectFactory, ProjectStageFactory

pytestmark = pytest.mark.django_db


def test_root_and_multilevel_children_have_defaults_and_timestamps():
    before = timezone.now()
    root = ProjectStageFactory()
    child = ProjectStageFactory(project=root.project, parent=root)
    grandchild = ProjectStageFactory(project=root.project, parent=child)
    assert root.project.stages.count() == 3
    assert root.children.get() == child
    assert child.children.get() == grandchild
    for stage in [root, child, grandchild]:
        stage.full_clean()
        stage.refresh_from_db()
        assert stage.description == ""
        assert stage.position == 0
        assert before <= stage.created_at <= stage.updated_at <= timezone.now()
        assert timezone.is_aware(stage.created_at)
    assert root.parent_id is None


def test_database_requires_project():
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        ProjectStage.objects.create(name="Sem obra")
    assert error.value.__cause__.diag.column_name == "project_id"


@pytest.mark.parametrize("name", ["", None])
def test_model_requires_name(name):
    stage = ProjectStageFactory.build(project=ProjectFactory(), name=name)
    with pytest.raises(ValidationError) as error:
        stage.full_clean()
    assert "name" in error.value.message_dict


def test_names_and_positions_need_not_be_unique():
    first = ProjectStageFactory(name="Etapa", position=1)
    second = ProjectStageFactory(project=first.project, name=first.name, position=1)
    child = ProjectStageFactory(
        project=first.project, parent=first, name=first.name, position=1
    )
    assert len({first.pk, second.pk, child.pk}) == 3


def test_database_blocks_negative_position():
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectStageFactory(position=-1)


def test_self_parent_is_blocked_in_model_and_database():
    stage = ProjectStageFactory()
    stage.parent = stage
    with pytest.raises(ValidationError) as error:
        stage.clean()
    assert "parent" in error.value.message_dict
    with pytest.raises(IntegrityError) as error, transaction.atomic():
        ProjectStage.objects.filter(pk=stage.pk).update(parent_id=stage.pk)
    assert (
        error.value.__cause__.diag.constraint_name
        == "projects_projectstage_not_self_parent"
    )
    stage.refresh_from_db()
    assert stage.parent_id is None


def test_parent_must_belong_to_same_project_even_within_tenant():
    parent = ProjectStageFactory()
    other = ProjectFactory(organization=parent.project.organization)
    stage = ProjectStageFactory.build(project=other, parent=parent)
    with pytest.raises(ValidationError) as error:
        stage.full_clean()
    assert "parent" in error.value.message_dict


def test_clean_rejects_cycle_and_terminates_on_preexisting_corruption():
    root = ProjectStageFactory()
    child = ProjectStageFactory(project=root.project, parent=root)
    leaf = ProjectStageFactory(project=root.project, parent=child)
    root.parent = leaf
    with pytest.raises(ValidationError):
        root.clean()
    root.refresh_from_db()
    assert root.parent_id is None
    # Direct ORM bypass can corrupt ancestry; validation must not loop indefinitely.
    ProjectStage.objects.filter(pk=root.pk).update(parent=leaf)
    candidate = ProjectStageFactory.build(project=root.project, parent=child)
    with pytest.raises(ValidationError):
        candidate.clean()


def test_restrict_preserves_children_but_project_cascade_removes_whole_tree():
    root = ProjectStageFactory()
    child = ProjectStageFactory(project=root.project, parent=root)
    ProjectStageFactory(project=root.project, parent=child)
    ProjectStageFactory(project=root.project)
    foreign = ProjectStageFactory()
    with pytest.raises(RestrictedError):
        root.delete()
    assert root.project.stages.count() == 4
    root.project.delete()
    assert ProjectStage.objects.count() == 1
    assert ProjectStage.objects.get() == foreign
