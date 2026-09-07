# Bale Project Conventions

1. Python code must follow the existing project's formatting/linting rules.
2. Reuse the project's existing HTTP, logging, settings, Celery and exception infrastructure when present.
3. Do not introduce a new Bale SDK unless there is a clear project requirement.
4. Prefer a small internal client over coupling business code to a third-party Telegram/Bale package.
5. Every new Bale feature should have a focused test for success and API failure.
