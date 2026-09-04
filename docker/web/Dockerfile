FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG REQUIREMENTS_FILE=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
