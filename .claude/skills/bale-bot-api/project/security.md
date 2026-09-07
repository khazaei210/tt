# Bale Security Rules

- Never commit `BALE_BOT_TOKEN`.
- Never print the token in logs.
- Never include a real token in tests/examples.
- Treat incoming webhook JSON as untrusted input.
- Validate callback data and authorization at the server.
- Use HTTPS for webhook endpoints.
- Apply request timeouts.
- Avoid leaking API responses containing sensitive user data into logs.
