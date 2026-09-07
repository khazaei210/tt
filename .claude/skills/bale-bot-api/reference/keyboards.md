# Bale Keyboards

Source: https://docs.bale.ai/

Documented keyboard-related types include:

- ReplyKeyboardMarkup
- KeyboardButton
- InlineKeyboardMarkup
- InlineKeyboardButton
- ReplyKeyboardRemove
- CopyTextButton

When implementing an inline button flow, also read `callbacks.md` because button presses generate CallbackQuery updates.

Do not assume every Telegram keyboard option exists in Bale; verify the local generated reference first.
