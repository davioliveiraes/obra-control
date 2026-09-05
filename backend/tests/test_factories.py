import pytest

from tests.factories.accounts import UserFactory


@pytest.mark.django_db
def test_user_factory_creates_user_through_manager_with_hashed_password():
    user = UserFactory(email="Factory@Example.COM", password="test-password")
    user.refresh_from_db()

    assert user.email == "factory@example.com"
    assert user.password != "test-password"
    assert user.check_password("test-password") is True


@pytest.mark.parametrize("strategy", ["build", "create"])
@pytest.mark.django_db
def test_user_factory_defaults_to_an_unusable_password(strategy):
    user = getattr(UserFactory, strategy)()
    assert user.has_usable_password() is False


def test_user_factory_build_does_not_leave_password_in_plain_text():
    user = UserFactory.build(password="test-password")
    assert user.pk is None
    assert user.password != "test-password"
    assert user.check_password("test-password") is True
