from .base import *  # noqa: F401,F403

DEBUG = False

# Set DJANGO_BEHIND_TLS_PROXY=False in .env for a plain-HTTP deployment with
# no TLS-terminating reverse proxy yet (e.g. reachable only by IP, no domain
# for a cert). Defaults to True since a proxy-fronted HTTPS deployment is
# the norm this file is otherwise written for — flip it back once a domain
# and TLS proxy (nginx, Caddy, a cloud load balancer) are in front of this.
BEHIND_TLS_PROXY = env.bool("DJANGO_BEHIND_TLS_PROXY", default=True)

SECURE_SSL_REDIRECT = BEHIND_TLS_PROXY
SESSION_COOKIE_SECURE = BEHIND_TLS_PROXY
CSRF_COOKIE_SECURE = BEHIND_TLS_PROXY
SECURE_HSTS_SECONDS = (60 * 60 * 24 * 7) if BEHIND_TLS_PROXY else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = BEHIND_TLS_PROXY
SECURE_HSTS_PRELOAD = BEHIND_TLS_PROXY

if BEHIND_TLS_PROXY:
    # gunicorn (docker/web/entrypoint.sh) speaks plain HTTP; SECURE_SSL_REDIRECT
    # and the secure-cookie settings above only make sense with a TLS-
    # terminating reverse proxy in front that forwards the original scheme via
    # this header. Only safe when that proxy is the sole way to reach this
    # service — otherwise a client could spoof the header directly and defeat
    # the SSL redirect. Not set at all when there's no such proxy (see above).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
