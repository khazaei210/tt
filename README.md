# Table Tennis Tournament Management System

A production-quality, extensible tournament management platform (individual,
doubles and team competitions; round-robin, knockout and group+knockout
formats). See `CLAUDE.md` for the full domain requirements and architecture
notes.

## Stack

- Django 5.2 (LTS) + PostgreSQL 18
- Django Templates + Tailwind CSS v4 + DaisyUI v5 + HTMX
- Docker Compose for local development

## Local development

1. Copy the environment template and adjust as needed:

   ```bash
   cp .env.example .env
   ```

2. Build and start the stack:

   ```bash
   docker compose up -d
   ```

   This starts three services:
   - `db` — PostgreSQL
   - `web` — Django dev server on http://localhost:8000
   - `tailwind` — watches templates and rebuilds `static/css/dist/styles.css`
     on change (Tailwind + DaisyUI)

3. Apply migrations:

   ```bash
   docker compose exec web python manage.py migrate
   ```

4. Create an admin user:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

5. Visit http://localhost:8000/ — you should see a page confirming the
   database connection and an HTMX round-trip.

### VPS firewall note

`docker-compose.yml` publishes the dev server's port 8000 to `0.0.0.0`, and
`DEBUG=True` in dev — reachable from the whole internet on a VPS with no
firewall. On this project's VPS, port 8000 is restricted to `localhost`
only at the host level: a systemd oneshot service,
`tt-port8000-firewall.service` (unit at
`/etc/systemd/system/tt-port8000-firewall.service`, script at
`/usr/local/sbin/tt-port8000-firewall.sh`), applies loopback-only iptables
rules to both the `INPUT` chain and Docker's `DOCKER-USER` chain (port 8000
is NAT'd by Docker, so a plain `INPUT` rule alone doesn't cover external
traffic) after `docker.service` starts, so the rule survives a reboot.

This lives outside the git repo (host-level config, not project code) and
would need to be recreated if this project ever moves to a different
server. If you need to reach the dev server from another machine, use an
SSH tunnel (`ssh -L 8000:localhost:8000 user@vps`) rather than opening the
port back up.

### Common commands

```bash
docker compose exec web python manage.py <command>   # any Django management command
docker compose logs -f web                            # tail Django logs
docker compose logs -f tailwind                       # tail CSS build logs
docker compose down                                   # stop everything
```

### Frontend build notes

Tailwind v4 uses CSS-first configuration — there is no `tailwind.config.js`.
Content sources are declared with `@source` directives in
`theme/src/input.css`. The compiled `static/css/dist/styles.css` is a build
artifact (git-ignored); in dev it's regenerated automatically by the
`tailwind` service. The production image (see below) builds it once, from a
dedicated Node stage in `docker/web/Dockerfile`, before `collectstatic` runs.

## Production deployment

```bash
cp .env.prod.example .env   # then fill in every value — see the file's comments
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

This builds the `docker/web/Dockerfile`'s `prod` target instead of `dev`:
the Tailwind/DaisyUI CSS is pre-built (no `tailwind` watcher service), the
source tree is copied into the image rather than bind-mounted, the
container runs as a non-root user, and gunicorn serves the app instead of
Django's dev server. `docker/web/entrypoint.sh` runs `collectstatic` at
container start (it needs real settings/env, which are only available at
deploy time) and then execs gunicorn; migrations are deliberately not
run automatically — see the entrypoint script's comment for why.

`config.settings.prod` turns on `SECURE_SSL_REDIRECT`, secure cookies, and
HSTS, all on the assumption that a TLS-terminating reverse proxy (nginx,
Caddy, a cloud load balancer) sits in front of this service and forwards
the original scheme via `X-Forwarded-Proto` — this repo does not include
that proxy. Don't expose the `web` container directly to the internet
without one in front of it.

## Project layout

```
apps/            Django apps (domain logic lives here, one app per bounded context)
config/          Django project settings, URLs, WSGI/ASGI
templates/       Base templates and shared components
static/          Static sources (vendor/ is committed, css/dist/ is generated)
theme/           Tailwind + DaisyUI build (Node, not part of the Python app)
docker/          Dockerfiles
requirements/    Python dependencies (base/dev/prod)
```

## Status

Phase 1 (infrastructure) complete: Docker, Django, PostgreSQL, Tailwind,
DaisyUI, HTMX and basic configuration are wired together and verified
end-to-end. No domain models exist yet — see `CLAUDE.md` sections 40–41 for
the phased roadmap and the current architecture proposal.
