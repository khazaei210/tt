from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

INSTALLED_APPS += [  # noqa: F405
    "debug_toolbar",
]

MIDDLEWARE += [  # noqa: F405
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]
