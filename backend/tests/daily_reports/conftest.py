import pytest

from tests.factories.daily_reports import DailyReportActivityFactory, DailyReportFactory
from tests.factories.projects import ProjectFactory, ProjectStageFactory
from tests.projects.conftest import api_client as api_client
from tests.projects.conftest import authenticated_client as authenticated_client
from tests.projects.conftest import membership as membership
from tests.projects.conftest import tenant_client as tenant_client
from tests.projects.conftest import user as user


@pytest.fixture
def project(membership):
    return ProjectFactory(organization=membership.organization)


@pytest.fixture
def report(project):
    return DailyReportFactory(project=project)


@pytest.fixture
def activity(report):
    return DailyReportActivityFactory(daily_report=report)


@pytest.fixture
def stage(project):
    return ProjectStageFactory(project=project)
