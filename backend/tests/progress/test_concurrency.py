from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.db import connections
from rest_framework.test import APIClient

from apps.progress.api.views import StageProgressEntryViewSet
from apps.progress.models import StageProgressEntry
from tests.factories.progress import StageProgressEntryFactory

from .test_api import detail, listing, payload


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_concurrent_stage_date_collision_returns_400(
    tenant_client, stage, monkeypatch, method
):
    entries = (
        [
            StageProgressEntryFactory(stage=stage, progress_date=date(2026, 9, day))
            for day in [1, 2]
        ]
        if method == "patch"
        else []
    )
    barrier = Barrier(2)
    original_save = StageProgressEntryViewSet._save_entry

    def synchronized_save(view, serializer, **kwargs):
        # Both requests pass actual validation before either writes to PostgreSQL.
        barrier.wait(timeout=15)
        return original_save(view, serializer, **kwargs)

    monkeypatch.setattr(StageProgressEntryViewSet, "_save_entry", synchronized_save)

    def send(index):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies.update(tenant_client.cookies)
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        url = detail(entries[index]) if entries else listing(stage)
        try:
            response = getattr(client, method)(
                url, payload(notes="Concorrente"), format="json"
            )
            return index, response.status_code, response.json()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send, i) for i in range(2)]
        results = [future.result(timeout=25) for future in futures]
    assert sorted(code for _, code, _ in results) == [200 if entries else 201, 400]
    assert (
        StageProgressEntry.objects.filter(
            stage=stage, progress_date=date(2026, 9, 9)
        ).count()
        == 1
    )
    assert StageProgressEntry.objects.filter(stage=stage).count() == (
        2 if entries else 1
    )
    index, _, response = next(result for result in results if result[1] == 400)
    assert response == {
        "progress_date": [
            "Já existe um registro de progresso para esta etapa nesta data."
        ]
    }
    if entries:
        entries[index].refresh_from_db()
        assert entries[index].progress_date == date(2026, 9, index + 1)
        assert entries[index].notes == ""
