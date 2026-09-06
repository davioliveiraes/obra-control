from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connections
from rest_framework.test import APIClient

from apps.planning.api.views import StagePlanViewSet
from apps.planning.models import StagePlan


@pytest.mark.django_db(transaction=True)
def test_concurrent_posts_return_created_and_validation_error(
    tenant_client, stage, monkeypatch
):
    # Only synchronize after normal validation. Both real inserts hit PostgreSQL.
    barrier = Barrier(2)
    original_create = StagePlanViewSet.perform_create

    def synchronized_create(view, serializer):
        barrier.wait(timeout=15)
        return original_create(view, serializer)

    monkeypatch.setattr(StagePlanViewSet, "perform_create", synchronized_create)

    def create_plan():
        client = APIClient(enforce_csrf_checks=True)
        client.cookies.update(tenant_client.cookies)
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        try:
            response = client.post(
                f"/api/v1/projects/{stage.project_id}/planning/",
                {
                    "stage_id": stage.pk,
                    "planned_start_date": "2026-10-01",
                    "planned_end_date": "2026-10-20",
                },
                format="json",
            )
            return response.status_code, response.json()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_plan)
        second = executor.submit(create_plan)
        results = sorted(
            [first.result(timeout=25), second.result(timeout=25)],
            key=lambda item: item[0],
        )
    assert [status for status, _ in results] == [201, 400]
    assert results[1][1] == {"stage_id": ["A etapa já possui planejamento."]}
    assert StagePlan.objects.filter(stage=stage).count() == 1
    assert StagePlan.objects.get(stage=stage).pk == results[0][1]["id"]
