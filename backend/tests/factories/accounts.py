import factory
from django.conf import settings


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = settings.AUTH_USER_MODEL

    email = factory.Sequence(lambda number: f"user{number}@example.com")
    password = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = model_class.objects.db_manager(cls._meta.database)
        return manager.create_user(*args, **kwargs)

    @classmethod
    def _build(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        user = model_class(*args, **kwargs)
        user.set_password(password)
        return user
