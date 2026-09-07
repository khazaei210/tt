# Bale Updates

Source: https://docs.bale.ai/

Bale currently documents two update delivery mechanisms:

- `getUpdates` (long polling)
- Webhook

Updates are JSON objects. At most one of the documented optional payload fields is present in an Update.

## Update fields currently documented

- `update_id`
- `message`
- `edited_message`
- `callback_query`
- `pre_checkout_query`

## getUpdates

Key parameters:

- `offset` — first update id to return; use the previous maximum `update_id + 1` to acknowledge consumed updates.
- `limit` — 1..100; default 100.
- `timeout` — long-polling wait in seconds.

After each response, recalculate the offset to avoid duplicate processing.

The official docs currently state that up to 2000 latest updates are retained for 24 hours until retrieved.
