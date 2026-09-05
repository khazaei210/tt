from .base import *  # noqa: F401,F403

DEBUG = False

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# gunicorn (docker/web/entrypoint.sh) speaks plain HTTP; SECURE_SSL_REDIRECT
# and the secure-cookie settings above only make sense with a TLS-
# terminating reverse proxy in front (nginx, Caddy, a cloud load balancer)
# that forwards the original scheme via this header. Only safe when that
# proxy is the sole way to reach this service — otherwise a client could
# spoof the header directly and defeat the SSL redirect.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
