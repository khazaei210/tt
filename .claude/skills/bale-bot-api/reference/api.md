# Bale Bot API — General API

Source: https://docs.bale.ai/

## Endpoint

`https://tapi.bale.ai/bot<TOKEN>/METHOD_NAME`

All requests use HTTPS.

## Request methods

- GET
- POST

## Parameter formats

- URL query string
- `application/x-www-form-urlencoded`
- `application/json` — not for file uploads
- `multipart/form-data` — use for file uploads

## Response contract

Success:

```json
{"ok": true, "result": {}}
```

Failure:

```json
{"ok": false, "error_code": 400, "description": "..."}
```

Some failures may include a `parameters` object.

Requests use UTF-8. API method names are not case-sensitive according to the official documentation.

## Authentication

The token is part of the URL. Store it outside source control, preferably in environment variables or Django settings.
