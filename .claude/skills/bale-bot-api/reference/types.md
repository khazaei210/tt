# Bale Bot API — Type Index

Source: https://docs.bale.ai/

The official docs currently list these major objects/types (the updater maintains the complete field-level snapshot):

- Update
- WebhookInfo
- User
- Chat
- ChatFullInfo
- Message
- MessageId
- MessageEntity
- PhotoSize
- Animation
- Audio
- Document
- Video
- Voice
- Contact
- Location
- Invoice
- File
- ReplyKeyboardMarkup
- KeyboardButton
- InlineKeyboardMarkup
- InlineKeyboardButton
- ReplyKeyboardRemove
- CallbackQuery
- WebAppData
- WebAppInfo
- CopyTextButton
- ChatMember
- ChatMemberOwner
- ChatMemberAdministrator
- ChatMemberMember
- ChatMemberRestricted
- ChatPhoto
- ResponseParameters
- InputMedia
- InputMediaPhoto
- InputMediaVideo
- InputMediaAnimation
- InputMediaAudio
- InputMediaDocument
- InputFile
- Sticker
- StickerSet
- LabeledPrice
- PreCheckoutQuery
- SuccessfulPayment
- Transaction

Important: fields marked optional by Bale may be absent, not merely null.

Some integer identifiers such as User/Chat IDs can exceed signed 32-bit range; use 64-bit-safe integer handling in application code.
