# Multi-stage: a "theme-build" stage compiles the production Tailwind/
# DaisyUI CSS (dev instead runs the `tailwind` compose service, which
# watches and rebuilds on change — no build step needed there), a shared
# "python-base" stage installs system packages, and two final targets:
# "dev" (source bind-mounted from the host, runs as root, Django's dev
# server — unchanged from before this file had stages) and "prod" (source
# copied into the image, non-root user, gunicorn). Select which one to
# build with `target: dev` / `target: prod` in docker-compose.

FROM node:24-alpine AS theme-build
WORKDIR /app/theme
COPY theme/package.json theme/package-lock.json ./
RUN npm ci
COPY theme/ ./
# Tailwind's @source directives (theme/src/input.css) point at these two
# directories to find the class names actually used in templates.
COPY templates/ /app/templates/
COPY apps/ /app/apps/
RUN npm run build


FROM python:3.12-slim AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*


FROM python-base AS dev
ARG REQUIREMENTS_FILE=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

# Runs as root: the source tree is bind-mounted from the host, and matching
# an arbitrary non-root UID to the host user adds bind-mount permission
# friction without a real security benefit in local development.

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM python-base AS prod
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt

COPY . .
# Overlay the compiled CSS from theme-build — collectstatic (run at
# container start, see entrypoint.sh, since it needs real settings/env)
# picks it up from static/css/dist alongside everything else in STATICFILES_DIRS.
COPY --from=theme-build /app/static/css/dist ./static/css/dist

RUN addgroup --system app \
    && adduser --system --ingroup app --home /app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["docker/web/entrypoint.sh"]
