#!/bin/sh
# Production entrypoint. Runs at every container start (not at image build
# time) so it always has the real environment (DJANGO_SECRET_KEY,
# DATABASE_URL, ...) available — collectstatic needs settings to import
# cleanly, which needs those to be set, and they're only known at deploy
# time via the .env file, not at `docker build` time.
#
# Migrations are deliberately NOT run here: applying them automatically on
# every container start is a footgun with more than one running instance
# (races, and a crash mid-migration retried by a container restart policy).
# Run `docker compose -f docker-compose.prod.yml exec web python manage.py
# migrate` explicitly instead.
set -e

python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${WEB_CONCURRENCY:-3}" \
    --access-logfile - \
    --error-logfile -
