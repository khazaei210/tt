# Bale Callback Queries

Source: https://docs.bale.ai/

An inline button interaction produces an Update containing `callback_query`. The callback query contains the data associated with the clicked button.

Typical processing flow:

1. Receive Update.
2. Detect `callback_query`.
3. Validate/parse callback data.
4. Execute the business action.
5. Call `answerCallbackQuery` when required by the UX/API flow.
6. Edit or send messages as appropriate.

Keep callback payloads compact and validate them server-side. Never trust callback data as authorization by itself.
