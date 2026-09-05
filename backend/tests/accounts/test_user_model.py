import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import User


def test_project_uses_custom_user():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []


def test_username_is_not_a_model_field():
    with pytest.raises(FieldDoesNotExist):
        User._meta.get_field("username")
    assert User.username is None


@pytest.mark.parametrize("email", [None, "", " ", "\t\n"])
def test_create_user_requires_email(email):
    with pytest.raises(ValueError, match="email address is required"):
        User.objects.create_user(email=email, password="test-password")


@pytest.mark.django_db
def test_create_user_persists_identity_and_hashes_password():
    user = User.objects.create_user(
        email="person@example.com",
        password="test-password",
        first_name="Ana",
        last_name="Silva",
    )
    user.refresh_from_db()

    assert user.email == "person@example.com"
    assert user.get_full_name() == "Ana Silva"
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.password != "test-password"
    assert user.check_password("test-password") is True
    assert user.check_password("incorrect-password") is False


@pytest.mark.django_db
def test_create_user_without_password_sets_unusable_password():
    user = User.objects.create_user(email="person@example.com")
    user.refresh_from_db()
    assert user.has_usable_password() is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "email", ["User@Example.com", "USER@EXAMPLE.COM", "  User@Example.COM  "]
)
def test_create_user_normalizes_email(email):
    user = User.objects.create_user(email=email)
    user.refresh_from_db()
    assert user.email == "user@example.com"


@pytest.mark.django_db
def test_model_save_normalizes_email_on_creation_and_update():
    user = User(email="  User@Example.COM  ")
    user.set_unusable_password()
    user.save()
    user.refresh_from_db()
    assert user.email == "user@example.com"

    user.email = "  Updated@Example.COM  "
    user.save(update_fields=["email"])
    user.refresh_from_db()
    assert user.email == "updated@example.com"


def test_model_clean_normalizes_email():
    user = User(email="  User@Example.COM  ")
    user.clean()
    assert user.email == "user@example.com"


@pytest.mark.parametrize("email", ["", "invalid-email"])
def test_model_validation_rejects_missing_or_invalid_email(email):
    user = User(email=email)
    user.set_unusable_password()
    with pytest.raises(ValidationError) as error:
        user.full_clean(validate_unique=False, validate_constraints=False)
    assert "email" in error.value.message_dict


@pytest.mark.django_db
def test_manager_cannot_create_case_variant_of_existing_email():
    User.objects.create_user(email="User@Example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(email="USER@example.com")
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_database_rejects_case_variant_even_when_save_is_bypassed():
    User.objects.create_user(email="user@example.com")
    other = User.objects.create_user(email="other@example.com")

    with pytest.raises(IntegrityError) as error, transaction.atomic():
        User.objects.filter(pk=other.pk).update(email="USER@EXAMPLE.COM")

    assert error.value.__cause__.diag.constraint_name == "accounts_user_email_ci_unique"
    other.refresh_from_db()
    assert other.email == "other@example.com"


@pytest.mark.django_db
def test_create_superuser_sets_required_flags_and_hashes_password():
    user = User.objects.create_superuser(
        email="Admin@Example.COM", password="test-password"
    )
    user.refresh_from_db()
    assert user.email == "admin@example.com"
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.is_active is True
    assert user.check_password("test-password") is True


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
@pytest.mark.parametrize("value", [False, None])
def test_create_superuser_rejects_incompatible_flags(flag, value):
    with pytest.raises(ValueError, match=f"{flag}=True"):
        User.objects.create_superuser(email="admin@example.com", **{flag: value})
