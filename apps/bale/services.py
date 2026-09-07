"""Application-level Bale operations: link a player's chat from a shared
contact, and notify players over their linked chat. Keeps business rules
(which player(s) a Participant represents, what a notification says) out
of the low-level client — apps.bale.client only knows how to call the API.
"""

import logging

from django.utils.translation import gettext as _

from apps.players.dashboard import build_player_dashboard
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
    """Dispatch one Bale Update (from getUpdates): links a player's chat
    (a shared Contact), replies to /start with the "share your phone
    number" prompt, or answers a linked player's next_games/my_rank
    command. Unknown/irrelevant updates are ignored: this bot has no
    other conversation surface yet."""
    message = update.get("message")
    if not message or "chat" not in message:
        return
    chat_id = message["chat"]["id"]
    contact = message.get("contact")
    if contact:
        _handle_contact_shared(chat_id, contact)
        return

    command = message.get("text", "").strip().lstrip("/").lower()
    if command == "start":
        _send_link_prompt(chat_id)
    elif command == "next_games":
        _handle_next_games(chat_id)
    elif command == "my_rank":
        _handle_my_rank(chat_id)


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


_NOT_LINKED_MESSAGE = _("You haven't linked your player profile yet — send /start and share your phone number first.")


def _player_for_chat(chat_id):
    return Player.objects.filter(bale_chat_id=chat_id).select_related("user").first()


def _handle_next_games(chat_id):
    """Reply to a linked player's next_games command with their upcoming
    matches — the same data/scope as players:dashboard on the site
    (apps.players.dashboard.build_player_dashboard), just as a Bale
    message instead of a web page."""
    client = BaleClient()
    player = _player_for_chat(chat_id)
    if player is None:
        client.call("sendMessage", chat_id=chat_id, text=_NOT_LINKED_MESSAGE)
        return

    dashboard = build_player_dashboard(player)
    if not dashboard.upcoming_matches:
        client.call("sendMessage", chat_id=chat_id, text=_("You have no upcoming matches."))
        return

    blocks = []
    for match in dashboard.upcoming_matches:
        when = match.start_time.strftime("%Y-%m-%d %H:%M") if match.start_time else _("Not scheduled yet")
        blocks.append(
            _("%(tournament)s — %(competition)s\nRound %(round)s: %(a)s vs %(b)s\n%(when)s")
            % {
                "tournament": match.competition.tournament.name,
                "competition": match.competition.name,
                "round": match.round_number,
                "a": match.participant_a or _("BYE"),
                "b": match.participant_b or _("BYE"),
                "when": when,
            }
        )
    client.call("sendMessage", chat_id=chat_id, text="\n\n".join(blocks))


def _handle_my_rank(chat_id):
    """Reply to a linked player's my_rank command with their current
    standing in every RankingCategory they appear in — the same data as
    rankings:my_rankings on the site, condensed into a chat message."""
    client = BaleClient()
    player = _player_for_chat(chat_id)
    if player is None:
        client.call("sendMessage", chat_id=chat_id, text=_NOT_LINKED_MESSAGE)
        return

    elo_ratings = list(player.elo_ratings.select_related("category").order_by("category__name"))
    rankings = {r.category_id: r for r in player.rankings.select_related("category")}
    if not elo_ratings and not rankings:
        client.call("sendMessage", chat_id=chat_id, text=_("You have no ranking yet."))
        return

    blocks = []
    seen_category_ids = set()
    for elo in elo_ratings:
        seen_category_ids.add(elo.category_id)
        ranking = rankings.get(elo.category_id)
        blocks.append(
            _("%(category)s\nElo: %(rating)s (#%(elo_rank)s)\nPoints: %(points)s (#%(points_rank)s)")
            % {
                "category": elo.category.name,
                "rating": round(elo.rating),
                "elo_rank": elo.current_rank or "—",
                "points": ranking.points if ranking else 0,
                "points_rank": ranking.current_rank if ranking and ranking.current_rank else "—",
            }
        )
    for category_id, ranking in rankings.items():
        if category_id in seen_category_ids:
            continue
        blocks.append(
            _("%(category)s\nPoints: %(points)s (#%(rank)s)")
            % {"category": ranking.category.name, "points": ranking.points, "rank": ranking.current_rank or "—"}
        )
    client.call("sendMessage", chat_id=chat_id, text="\n\n".join(blocks))
