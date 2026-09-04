FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

ARG REQUIREMENTS_FILE=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

# Runs as root in this dev-oriented image: the source tree is bind-mounted
# from the host, and matching an arbitrary non-root UID to the host user
# adds bind-mount permission friction without a real security benefit in
# local development. Production hardening (CLAUDE.md phase 10) should build
# a separate image that copies (not bind-mounts) the source and drops to a
# non-root user.

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
