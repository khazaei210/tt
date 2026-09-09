"""Self-service registration: a logged-in user with a Player profile
registering (or withdrawing) themselves for an Individual competition,
as opposed to apps.tournaments.forms.ParticipantForm/BulkParticipantForm
which are staff-only. Kept as its own module/service (CLAUDE.md section
11) so eligibility/capacity rules are enforced identically regardless of
who's adding the participant.
"""

from django.utils.translation import gettext_lazy as _

from apps.players.models import Player

from ..models import AuditAction, Participant, ParticipantType, TournamentAuditLog


class RegistrationClosedError(Exception):
    pass


class CompetitionFullError(Exception):
    pass


class UnsupportedParticipantTypeError(Exception):
    pass


class NoPlayerProfileError(Exception):
    pass


class AlreadyRegisteredError(Exception):
    pass


class NotRegisteredError(Exception):
    pass


class CannotWithdrawError(Exception):
    pass


def is_competition_full(competition):
    if competition.registration_capacity is None:
        return False
    return competition.participants.entrants().count() >= competition.registration_capacity


def register_self(competition, user):
    """Register the given user's own Player profile as an Individual
    participant in the competition. Raises a specific exception for each
    reason registration might not be allowed."""
    if not competition.registration_open:
        raise RegistrationClosedError(_("Registration for this competition is closed."))
    if competition.participant_type != ParticipantType.INDIVIDUAL:
        raise UnsupportedParticipantTypeError(_("Self-registration is only available for individual competitions."))
    player = getattr(user, "player_profile", None)
    if player is None:
        raise NoPlayerProfileError(_("You need a player profile before you can register."))
    if competition.participants.filter(individual_player=player).exists():
        raise AlreadyRegisteredError(_("You are already registered for this competition."))
    if is_competition_full(competition):
        raise CompetitionFullError(_("This competition has reached its registration capacity."))

    participant = Participant.objects.create(
        competition=competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
    )
    TournamentAuditLog.objects.log(
        competition.tournament,
        user,
        AuditAction.REGISTERED,
        _("%(player)s registered for %(competition)s.") % {"player": player.full_name, "competition": competition.name},
    )
    return participant


def unregister_self(competition, user):
    """Withdraw the given user's own registration from the competition.
    Raises CannotWithdrawError once the participant already has matches
    (draw/schedule already generated) — mirrors the RESTRICT on
    Match.participant_a/b, but as a clean domain error instead of letting
    a low-level RestrictedError surface to the view."""
    player = getattr(user, "player_profile", None)
    participant = None
    if player is not None:
        participant = competition.participants.filter(individual_player=player).first()
    if participant is None:
        raise NotRegisteredError(_("You are not registered for this competition."))
    if participant.matches_as_participant_a.exists() or participant.matches_as_participant_b.exists():
        raise CannotWithdrawError(_("You can't withdraw once the draw/schedule already includes you — contact a tournament manager."))

    TournamentAuditLog.objects.log(
        competition.tournament,
        user,
        AuditAction.UNREGISTERED,
        _("%(player)s withdrew from %(competition)s.") % {"player": player.full_name, "competition": competition.name},
    )
    participant.delete()
