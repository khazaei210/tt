# Project Bale Architecture

Recommended boundary:

Business/domain code -> Bale service -> Bale client -> Bale API

## Client responsibilities

- Construct the API URL.
- Attach the bot token.
- Encode parameters correctly.
- Perform HTTP calls.
- Parse the common response envelope.
- Raise project-specific exceptions for transport/API failures.
- Apply timeouts and logging without exposing secrets.

## Service responsibilities

- Application-level operations such as notify user, send document, build a keyboard, etc.
- Keep business rules out of the low-level HTTP client.

## Webhook responsibilities

- Accept JSON update.
- Validate and normalize it.
- Dispatch to handlers.
- Return promptly.
- Use Celery for slow work where needed.

## Idempotency

Webhook/update processing should tolerate duplicate delivery. Use `update_id` or a suitable application-level idempotency key.
