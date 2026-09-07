# Django Integration

Use Django settings/environment variables for configuration.

Example settings:

```python
BALE_BOT_TOKEN = env("BALE_BOT_TOKEN")
BALE_API_BASE_URL = "https://tapi.bale.ai"
BALE_API_TIMEOUT = 15
```

Prefer a dedicated app/module such as:

```text
bale/
  client.py
  services.py
  exceptions.py
  webhook.py
  handlers.py
  keyboards.py
```

Do not put raw Bale HTTP calls in models or unrelated views.

If a user-facing business transaction must not fail because Bale is unavailable, enqueue the notification after the transaction and handle retries asynchronously.
