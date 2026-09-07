# Bale Webhooks

Source: https://docs.bale.ai/

## Methods

- `setWebhook`
- `deleteWebhook`
- `getWebhookInfo`

`setWebhook` accepts an HTTPS URL. An empty URL disables the webhook. The current official docs list ports `443` and `88` as supported webhook ports.

`deleteWebhook` is used when switching back to `getUpdates`.

`getWebhookInfo` returns the current webhook status. If `getUpdates` is in use, the documented `url` field is empty.

## Django guidance

Webhook endpoint should:

1. Validate the request as required by the application.
2. Parse JSON.
3. Detect the update type.
4. Return quickly.
5. Delegate slow work to Celery where appropriate.
6. Make processing idempotent using `update_id` or an application-level deduplication strategy.
