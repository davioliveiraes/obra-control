from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connections
from rest_framework.test import APIClient

from tests.factories.projects import ProjectFactory, ProjectStageFactory


@pytest.mark.django_db(transaction=True)
def test_concurrent_parent_changes_cannot_form_a_cycle(tenant_client, membership):
    project = ProjectFactory(organization=membership.organization)
    first = ProjectStageFactory(project=project)
    second = ProjectStageFactory(project=project)
    barrier = Barrier(2)

    def reparent(stage_id, parent_id):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies.update(tenant_client.cookies)
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        try:
            barrier.wait(timeout=10)
            return client.patch(
                f"/api/v1/projects/{project.pk}/stages/{stage_id}/",
                {"parent_id": parent_id},
                format="json",
            ).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        one = executor.submit(reparent, first.pk, second.pk)
        two = executor.submit(reparent, second.pk, first.pk)
        assert sorted([one.result(timeout=20), two.result(timeout=20)]) == [200, 400]
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.parent_id, second.parent_id) in [(None, first.pk), (second.pk, None)]
