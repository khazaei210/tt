# Bale Bot API Skill

## Purpose

This skill gives Claude Code a reliable, project-local knowledge base for integrating the official Bale Bot API.

Official source: https://docs.bale.ai/
API base: `https://tapi.bale.ai/bot<TOKEN>/METHOD_NAME`

## Source-of-truth rule

Bale's API is based on Telegram Bot API concepts, but it has differences. Never infer that a Telegram method, field, limit, update type, or behavior exists in Bale without checking the local reference or official documentation.

Priority:
1. Official Bale documentation.
2. This skill's generated reference snapshot.
3. Project-specific conventions under `project/`.
4. General Telegram knowledge only as a hypothesis, never as proof.

## Before coding

1. Identify the Bale method/type involved.
2. Read the relevant section in `reference/`.
3. Check request parameters, response type, optional fields and limitations.
4. Check `project/` rules.
5. Implement through the project's Bale client/service abstraction.
6. Add or update tests.

## Security

Never hard-code or commit the Bale bot token. Use environment variables or Django settings. Never put real credentials in examples, logs, tests, CLAUDE.md, or documentation.

## Django architecture

Prefer:

Django business logic -> Bale service -> Bale client -> Bale HTTP API

Do not scatter direct `requests`/HTTP calls throughout Django views or models.

For webhook handlers, parse and validate the update quickly; delegate long-running work to Celery where appropriate.

## API behavior to remember

- Requests use HTTPS.
- Endpoint form: `https://tapi.bale.ai/bot<TOKEN>/METHOD_NAME`.
- GET and POST are supported.
- Parameters can be sent using query string, `application/x-www-form-urlencoded`, `application/json`, or `multipart/form-data` for file uploads.
- Responses are JSON and contain an `ok` boolean; successful responses put the result in `result`; failures include `error_code` and may include `parameters`.
- Updates are available through `getUpdates` or Webhook.
- The current official docs state that the latest 2000 messages/updates are retained for 24 hours until retrieved.

## Current reference

The generated reference is maintained by `tools/bale/update_docs.py`.
Run it when official documentation changes or before a significant Bale integration change.

## If documentation is missing

Do not invent behavior. Say which official Bale detail is missing and ask for clarification or consult the official source.
