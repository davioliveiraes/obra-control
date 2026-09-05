from django.contrib.auth import get_user_model
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return get_user_model().objects.normalize_email(value)


class UserIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ("id", "email", "first_name", "last_name")
        read_only_fields = fields


class CsrfTokenSerializer(serializers.Serializer):
    csrfToken = serializers.CharField(read_only=True)
