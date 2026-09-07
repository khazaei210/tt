"""Reply keyboards for the Bale bot conversation.

Bale's ReplyKeyboardMarkup/KeyboardButton shape mirrors what's documented
in .claude/skills/bale-bot-api/reference/official.md — a KeyboardButton
with request_contact=True makes pressing it send the user's phone number
as a Contact update, which apps.bale.services uses to link a Player.
"""

from django.utils.translation import gettext as _


def build_contact_request_keyboard():
    return {
        "keyboard": [[{"text": _("Share my phone number"), "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }
