"""Production settings with mandatory secrets and host configuration."""

from .base import *  # noqa: F403
from .base import required_env, required_env_list

DEBUG = False
SECRET_KEY = required_env("DJANGO_SECRET_KEY")
required_env("POSTGRES_PASSWORD")
ALLOWED_HOSTS = required_env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = required_env_list("CSRF_TRUSTED_ORIGINS")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
X_FRAME_OPTIONS = "DENY"
