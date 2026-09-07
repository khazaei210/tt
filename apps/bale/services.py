"""Application-level Bale operations: link a player's chat from a shared
contact, and notify players over their linked chat. Keeps business rules
(which player(s) a Participant represents, what a notification says) out
of the low-level client — apps.bale.client only knows how to call the API.
"""

import logging

from django.utils.translation import gettext as _

from apps.players.models import Player
from apps.players.phone import normalize_mobile_number

from .client import BaleAPIError, BaleClient
from .exceptions import BaleNotLinkedError
from .keyboards import build_contact_request_keyboard

logger = logging.getLogger(__name__)


def password_reset_message(username, raw_password):
    return _("Your account password has been reset.\nUsername: %(username)s\nNew password: %(password)s") % {
        "username": username,
        "password": raw_password,
    }


def send_password_reset_notification(player, username, raw_password):
    """Best-effort: tell a player their password was reset, over their
    linked Bale chat. Returns "sent", "not_linked", or "failed" — never
    raises, since the password has already been reset by the time any
    caller reaches this; a Bale problem must not turn that into a 500
    that hides the new password from the staff member who reset it.
    """
    try:
        notify_player(player, password_reset_message(username, raw_password))
    except BaleNotLinkedError:
        return "not_linked"
    except BaleAPIError as exc:
        logger.warning("Failed to send password reset to player %s via Bale: %s", player.pk, exc)
        return "failed"
    except Exception:
        logger.exception("Unexpected error sending a password reset to player %s via Bale", player.pk)
        return "failed"
    return "sent"


def notify_player(player, text):
    """Send text to a Player's linked Bale chat. Raises BaleNotLinkedError
    if the player hasn't linked one yet, or BaleAPIError on a transport/API
    failure — the caller decides how to surface either (a status message,
    a best-effort log-and-continue loop, etc.); this never sends partial
    output or retries silently.
    """
    if not player.bale_chat_id:
        raise BaleNotLinkedError(player)
    BaleClient().call("sendMessage", chat_id=player.bale_chat_id, text=text)


def _players_for_participant(participant):
    """Every Player a Participant represents, regardless of participant
    type — the same generic-Participant handling the draw/match engine
    uses (CLAUDE.md section 7), so a notification reaches a doubles pair
    or a whole team roster, not just an individual entrant."""
    if participant.individual_player_id:
        return [participant.individual_player]
    if participant.doubles_pair_id:
        pair = participant.doubles_pair
        return [pair.player_one, pair.player_two]
    if participant.team_id:
        return list(
            Player.objects.filter(
                team_memberships__team_id=participant.team_id,
                team_memberships__is_active=True,
            )
        )
    return []


def _match_notification_text(match, opponent):
    tournament = match.competition.tournament
    return _(
        "New match assigned:\n%(tournament)s — %(competition)s\nRound %(round)s\nOpponent: %(opponent)s"
    ) % {
        "tournament": tournament.name,
        "competition": match.competition.name,
        "round": match.round_number,
        "opponent": str(opponent) if opponent else _("BYE"),
    }


def notify_matches_created(matches):
    """Best-effort: tell every player involved in each match who they're
    playing. Never raises — a Bale outage or an unlinked player must not
    break draw/schedule generation, which is what calls this right after
    creating the matches. Returns [(player, "sent"|"not_linked"|<error>)]
    so the caller can report a summary to staff.
    """
    results = []
    for match in matches:
        if match.is_bye or match.participant_a_id is None or match.participant_b_id is None:
            continue
        for participant, opponent in (
            (match.participant_a, match.participant_b),
            (match.participant_b, match.participant_a),
        ):
            if participant.is_bye:
                continue
            for player in _players_for_participant(participant):
                text = _match_notification_text(match, opponent)
                try:
                    notify_player(player, text)
                except BaleNotLinkedError:
                    results.append((player, "not_linked"))
                except BaleAPIError as exc:
                    logger.warning("Failed to notify player %s of match %s: %s", player.pk, match.pk, exc)
                    results.append((player, str(exc)))
                else:
                    results.append((player, "sent"))
    return results


def handle_update(update):
    """Dispatch one Bale Update (from getUpdates) — either links a
    player's chat (a shared Contact) or replies to /start with the
    "share your phone number" prompt. Unknown/irrelevant updates are
    ignored: this bot has no other conversation surface yet."""
    message = update.get("message")
    if not message or "chat" not in message:
        return
    chat_id = message["chat"]["id"]
    contact = message.get("contact")
    if contact:
        _handle_contact_shared(chat_id, contact)
        return
    if message.get("text", "").strip() == "/start":
        _send_link_prompt(chat_id)


def _handle_contact_shared(chat_id, contact):
    phone = normalize_mobile_number(contact.get("phone_number", ""))
    client = BaleClient()
    if not phone:
        return
    player = Player.objects.filter(mobile_number=phone).first()
    if player is None:
        client.call(
            "sendMessage",
            chat_id=chat_id,
            text=_("No player profile was found with this phone number. Ask a tournament manager to add it to your profile, then try again."),
        )
        return
    player.bale_chat_id = chat_id
    player.save(update_fields=["bale_chat_id"])
    client.call(
        "sendMessage",
        chat_id=chat_id,
        text=_("You're linked, %(name)s! Match notifications will be sent here.") % {"name": player.full_name},
    )


def _send_link_prompt(chat_id):
    BaleClient().call(
        "sendMessage",
        chat_id=chat_id,
        text=_("Welcome! Share your phone number to link your player profile and receive match notifications."),
        reply_markup=build_contact_request_keyboard(),
    )
