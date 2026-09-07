# Bale Bot API — Method Index

Source: https://docs.bale.ai/

This index is intentionally kept compact. The updater can refresh the field-level documentation from the official page.

## Core

- getMe
- sendMessage
- forwardMessage
- copyMessage
- sendPhoto
- sendAudio
- sendDocument
- sendVideo
- sendAnimation
- sendVoice
- sendMediaGroup
- sendLocation
- sendContact
- sendChatAction
- getFile
- answerCallbackQuery
- askReview

## Chat administration

- banChatMember
- unbanChatMember
- promoteChatMember
- setChatPhoto
- leaveChat
- getChat
- getChatAdministrators
- getChatMembersCount
- getChatMember
- pinChatMessage
- unPinChatMessage
- unpinAllChatMessages
- setChatTitle
- setChatDescription
- deleteChatPhoto
- createChatInviteLink
- revokeChatInviteLink
- exportChatInviteLink

## Message updates

- editMessageText
- editMessageCaption
- editMessageReplyMarkup
- deleteMessage

## Stickers

- uploadStickerFile
- createNewStickerSet
- addStickerToSet

## Payments

- sendInvoice
- createInvoiceLink
- answerPreCheckoutQuery
- inquireTransaction

## Update delivery

- getUpdates
- setWebhook
- deleteWebhook
- getWebhookInfo

For exact parameters and return types, use the generated `official.md` or refresh the reference with `tools/bale/update_docs.py`.
