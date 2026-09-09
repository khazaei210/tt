"""Automation for the tedious parts of tournament setup (CLAUDE.md section
11: draw/seeding algorithms belong in their own testable service, not
embedded in views): seeding a competition's participants from their
current Elo rating, and auto-distributing a round-robin stage's
participants across its already-created groups.
"""

import math
import string

from django.db.models import F, Max
from django.utils.translation import gettext_lazy as _

from apps.rankings.models import EloRating

from ..models import AuditAction, Group, GroupParticipant, StageFormat, TournamentAuditLog


class NotRoundRobinStageError(Exception):
    pass


class NoGroupsAvailableError(Exception):
    pass


class StageLockedError(Exception):
    pass


class DuplicateGroupAssignmentError(Exception):
    pass


class InvalidGroupMoveError(Exception):
    pass


def ensure_stage_unlocked(stage):
    if stage.is_locked:
        raise StageLockedError(_("This stage's draw is locked. An administrator must unlock it before making changes."))


def lock_stage(stage, *, performed_by=None):
    stage.is_locked = True
    stage.save(update_fields=["is_locked"])
    TournamentAuditLog.objects.log(
        stage.competition.tournament, performed_by, AuditAction.STAGE_LOCKED, _("Locked %(stage)s.") % {"stage": stage.name}
    )
    return stage


def unlock_stage(stage, *, performed_by=None):
    stage.is_locked = False
    stage.save(update_fields=["is_locked"])
    TournamentAuditLog.objects.log(
        stage.competition.tournament, performed_by, AuditAction.STAGE_UNLOCKED, _("Unlocked %(stage)s.") % {"stage": stage.name}
    )
    return stage


def attach_elo_ratings(participants, category):
    """Best-effort: annotate each participant with its player(s)' current
    Elo rating/rank in the given ranking category, so staff can see global
    form at a glance while managing entrants. Left None if category is
    None, or for team participants (ranking isn't attributed to
    individual players for teams — same scope limit as
    apps.rankings.services.players_for_participant). Doubles show the
    average of both players' ratings.
    """
    for participant in participants:
        participant.elo_rating = None
        participant.elo_rank = None
    if category is None:
        return

    player_ids = set()
    for participant in participants:
        if participant.individual_player_id:
            player_ids.add(participant.individual_player_id)
        elif participant.doubles_pair_id:
            player_ids.add(participant.doubles_pair.player_one_id)
            player_ids.add(participant.doubles_pair.player_two_id)
    if not player_ids:
        return

    ratings = {r.player_id: r for r in EloRating.objects.filter(category=category, player_id__in=player_ids)}
    for participant in participants:
        if participant.individual_player_id:
            rating = ratings.get(participant.individual_player_id)
            if rating:
                participant.elo_rating = rating.rating
                participant.elo_rank = rating.current_rank
        elif participant.doubles_pair_id:
            values = [
                ratings[pid].rating
                for pid in (participant.doubles_pair.player_one_id, participant.doubles_pair.player_two_id)
                if pid in ratings
            ]
            if values:
                participant.elo_rating = sum(values) / len(values)


def seed_participants_by_rating(competition):
    """Recompute every non-BYE participant's seed from their current Elo
    rating in the competition's ranking category — highest rating becomes
    seed 1. Unrated participants (no ranking_category configured, or no
    EloRating yet) sort after every rated one, ordered by name for a
    deterministic result, and still receive the next seed numbers rather
    than being left blank. Overwrites any seed already set — this is a
    full reseed, not a fill-in-the-gaps operation.
    """
    participants = list(
        competition.participants.entrants().select_related(
            "individual_player", "doubles_pair__player_one", "doubles_pair__player_two", "team"
        )
    )
    attach_elo_ratings(participants, competition.ranking_category)
    participants.sort(key=lambda p: (p.elo_rating is None, -(p.elo_rating or 0), p.display_name))

    changed = []
    for index, participant in enumerate(participants, start=1):
        if participant.seed != index:
            participant.seed = index
            changed.append(participant)
    for participant in changed:
        participant.save(update_fields=["seed"])
    return participants


def auto_assign_participants_to_groups(stage):
    """Distribute a round-robin stage's not-yet-grouped competition
    participants across its existing groups: in seed order (unseeded
    participants last, then by id for determinism), each participant goes
    into whichever group currently has the fewest members — the standard
    way to keep groups evenly sized no matter how many participants are
    already placed by hand. Doesn't touch existing GroupParticipant rows.

    Raises NotRoundRobinStageError if the stage isn't round-robin, or
    NoGroupsAvailableError if it has no groups yet — a manager must create
    at least one group first (this only assigns participants to groups
    that already exist, it doesn't create groups).
    """
    ensure_stage_unlocked(stage)
    if stage.stage_format != StageFormat.ROUND_ROBIN:
        raise NotRoundRobinStageError(_("Only a round-robin stage's groups can be auto-assigned."))
    groups = list(stage.groups.order_by("order"))
    if not groups:
        raise NoGroupsAvailableError(_("Create at least one group before auto-assigning participants."))

    already_grouped_ids = set(
        GroupParticipant.objects.filter(group__stage=stage).values_list("participant_id", flat=True)
    )
    unassigned = list(
        stage.competition.participants.entrants()
        .exclude(pk__in=already_grouped_ids)
        .order_by(F("seed").asc(nulls_last=True), "id")
    )
    if not unassigned:
        return []

    counts = {group.id: group.group_participants.count() for group in groups}
    created = []
    for participant in unassigned:
        target = min(groups, key=lambda g: (counts[g.id], g.order))
        created.append(GroupParticipant(group=target, participant=participant))
        counts[target.id] += 1
    GroupParticipant.objects.bulk_create(created)
    return created


def suggested_group_count(participant_count, target_group_size=4):
    """A sizing hint for the "how many groups?" field — not enforced, the
    administrator still makes the actual call (per the requirement that
    the admin "determine[s] the number of groups")."""
    if participant_count < 1:
        return 1
    return max(1, math.ceil(participant_count / target_group_size))


def _group_name_candidates():
    for letter in string.ascii_uppercase:
        yield f"{_('Group')} {letter}"
    n = len(string.ascii_uppercase) + 1
    while True:
        yield f"{_('Group')} {n}"
        n += 1


def create_groups(stage, count, *, performed_by=None):
    """Create `count` new Group rows for a round-robin stage in one call,
    named "Group A", "Group B", ... continuing after any groups that
    already exist (skipping any name already taken). Doesn't assign
    participants — pair with auto_assign_participants_to_groups for that.
    """
    ensure_stage_unlocked(stage)
    if stage.stage_format != StageFormat.ROUND_ROBIN:
        raise NotRoundRobinStageError(_("Only a round-robin stage can have groups."))
    if count < 1:
        raise ValueError("count must be at least 1")

    existing_names = set(stage.groups.values_list("name", flat=True))
    next_order = (stage.groups.aggregate(Max("order"))["order__max"] or 0) + 1

    created = []
    for name in _group_name_candidates():
        if len(created) >= count:
            break
        if name in existing_names:
            continue
        created.append(Group(stage=stage, name=name, order=next_order + len(created)))
    Group.objects.bulk_create(created)
    TournamentAuditLog.objects.log(
        stage.competition.tournament,
        performed_by,
        AuditAction.GROUPS_CREATED,
        _("Created %(n)s group(s) for %(stage)s.") % {"n": len(created), "stage": stage.name},
    )
    return created


def move_participant_to_group(group_participant, target_group, *, performed_by=None):
    """Move an already-placed participant to a different group within the
    same stage — the manual fix-up step after an automatic (or another
    manual) group draw. Unlike remove-then-add, this is a single
    validated operation so a partial failure can't leave the participant
    in neither group.
    """
    current_group = group_participant.group
    stage = current_group.stage
    ensure_stage_unlocked(stage)
    if target_group.stage_id != stage.id:
        raise InvalidGroupMoveError(_("The target group must belong to the same stage."))
    if target_group.id == current_group.id:
        raise InvalidGroupMoveError(_("The participant is already in that group."))
    if GroupParticipant.objects.filter(group=target_group, participant_id=group_participant.participant_id).exists():
        raise DuplicateGroupAssignmentError(_("This participant is already assigned to the target group."))

    participant_name = group_participant.participant.display_name
    group_participant.group = target_group
    group_participant.save(update_fields=["group"])
    TournamentAuditLog.objects.log(
        stage.competition.tournament,
        performed_by,
        AuditAction.PARTICIPANT_MOVED,
        _("Moved %(participant)s from %(from)s to %(to)s.")
        % {"participant": participant_name, "from": current_group.name, "to": target_group.name},
    )
    return group_participant
