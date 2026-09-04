import sys

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# The debug toolbar has no business running during automated tests: it
# injects its panel into every HTML response, which resolves its own
# static assets through django.contrib.staticfiles storage — a manifest
# lookup that fails outside a real collectstatic'd deployment.
TESTING = "test" in sys.argv

if not TESTING:
    INSTALLED_APPS += [  # noqa: F405
        "debug_toolbar",
    ]

    MIDDLEWARE += [  # noqa: F405
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    ]

if TESTING:
    # Manifest-based static storage requires a real collectstatic run to
    # produce staticfiles.json; tests shouldn't need to run that asset
    # pipeline step just to render a page containing a {% static %} tag.
    STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"  # noqa: F405

    # PBKDF2 (the default) is deliberately slow; tests that create many
    # users via create_user()/create_superuser() don't need that cost.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

INTERNAL_IPS = ["127.0.0.1"]
