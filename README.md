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
artifact (git-ignored); it is regenerated automatically by the `tailwind`
service in dev. A production image build should run
`npm --prefix theme ci && npm --prefix theme run build` before
`collectstatic` — not yet wired into `docker/web/Dockerfile`, which currently
targets local development only.

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
