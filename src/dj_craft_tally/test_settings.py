"""Minimal Django settings used by this package's test suite."""

SECRET_KEY = "tests-only-secret-key"  # noqa: S105
INSTALLED_APPS = ["django.contrib.contenttypes", "dj_craft_tally"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
