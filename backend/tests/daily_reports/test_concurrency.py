from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.db import connections
from rest_framework.test import APIClient

from apps.daily_reports.api.views import DailyReportViewSet
from apps.daily_reports.models import DailyReport
from tests.factories.daily_reports import DailyReportFactory

from .test_api import detail, listing


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_concurrent_date_collision_returns_400_without_partial_save(
    tenant_client, project, monkeypatch, method
):
    reports = (
        [
            DailyReportFactory(project=project, report_date=date(2026, 9, day))
            for day in [1, 2]
        ]
        if method == "patch"
        else []
    )
    barrier = Barrier(2)
    original_save = DailyReportViewSet._save_report

    def synchronized_save(view, serializer, **kwargs):
        # Both requests have passed real validation before either writes.
        barrier.wait(timeout=15)
        return original_save(view, serializer, **kwargs)

    monkeypatch.setattr(DailyReportViewSet, "_save_report", synchronized_save)

    def send_request(index):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies.update(tenant_client.cookies)
        client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        url = detail(reports[index]) if reports else listing(project)
        try:
            response = getattr(client, method)(
                url,
                {"report_date": "2026-09-08", "general_notes": "Concorrente"},
                format="json",
            )
            return index, response.status_code, response.json()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send_request, i) for i in range(2)]
        results = [future.result(timeout=25) for future in futures]
    assert sorted(code for _, code, _ in results) == [200 if reports else 201, 400]
    assert (
        DailyReport.objects.filter(
            project=project, report_date=date(2026, 9, 8)
        ).count()
        == 1
    )
    assert DailyReport.objects.filter(project=project).count() == (2 if reports else 1)
    index, _, payload = next(result for result in results if result[1] == 400)
    assert payload == {"report_date": ["Já existe um RDO para esta obra nesta data."]}
    if reports:
        reports[index].refresh_from_db()
        assert reports[index].report_date == date(2026, 9, index + 1)
        assert reports[index].general_notes == ""
