"""Smoke tests for the backend foundation."""

import os

from django.conf import settings
from django.core.checks import run_checks


def test_django_initializes() -> None:
    assert settings.configured


def test_test_settings_are_loaded() -> None:
    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.test"


def test_timezone_support_is_enabled() -> None:
    assert settings.USE_TZ is True


def test_postgresql_is_the_configured_database() -> None:
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def test_django_system_checks_pass() -> None:
    assert run_checks() == []
