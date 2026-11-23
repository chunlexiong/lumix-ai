import os

from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env_bool("DJANGO_DEBUG", True)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-development-key-change-before-deploying",
)

# SECURITY WARNING: define the correct hosts in production!
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", False)
SECURE_CONTENT_TYPE_NOSNIFF = env_bool("SECURE_CONTENT_TYPE_NOSNIFF", True)
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", "1209600"))
SESSION_SAVE_EVERY_REQUEST = env_bool("SESSION_SAVE_EVERY_REQUEST", False)
USE_X_FORWARDED_HOST = env_bool("USE_X_FORWARDED_HOST", False)

proxy_ssl_header = os.getenv("SECURE_PROXY_SSL_HEADER", "").strip()
SECURE_PROXY_SSL_HEADER = tuple(proxy_ssl_header.split(",", 1)) if proxy_ssl_header else None

if not EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


try:
    from .local import *
except ImportError:
    pass
