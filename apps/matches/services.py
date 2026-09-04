from django.db import transaction
from django.db.models import F, Max
from django.utils.translation import gettext_lazy as _

from apps.tournaments.services.knockout import generate_knockout_bracket
from apps.tournaments.services.round_robin import generate_round_robin

from .models import Match, MatchSet, MatchStatus
from .scoring import compute_match_result, validate_set_score


class ScheduleAlreadyGeneratedError(Exception):
    pass


class NotEnoughParticipantsError(Exception):
    pass


class MatchAlreadyCompletedError(Exception):
    pass


class InvalidSetNumberError(Exception):
    pass


@transaction.atomic
def generate_group_schedule(group, *, legs=1, seed=None):
    """Generate and persist a round-robin schedule for a Group.

    Raises ScheduleAlreadyGeneratedError if the group already has matches
    (regenerating requires clearing the existing schedule first, since
    Match rows are the source of truth once created) and
    NotEnoughParticipantsError if the group has fewer than 2 participants.
    """
    if group.matches.exists():
        raise ScheduleAlreadyGeneratedError(_("This group already has a generated schedule."))

    participant_ids = list(group.group_participants.values_list("participant_id", flat=True))
    if len(participant_ids) < 2:
        raise NotEnoughParticipantsError(_("A group needs at least two participants to generate a schedule."))

    schedule = generate_round_robin(participant_ids, legs=legs, seed=seed)

    matches = [
        Match(
            competition_id=group.stage.competition_id,
            stage_id=group.stage_id,
            group=group,
            round_number=fixture.round_number,
            participant_a_id=fixture.participant_a,
            participant_b_id=fixture.participant_b,
        )
        for fixture in schedule.fixtures
    ]
    Match.objects.bulk_create(matches)
    return schedule


@transaction.atomic
def clear_group_schedule(group):
    group.matches.all().delete()


def _get_or_create_bye_participant(competition):
    from apps.tournaments.models import Participant

    bye, _created = Participant.objects.get_or_create(
        competition=competition,
        is_bye=True,
        defaults={"participant_type": competition.participant_type},
    )
    return bye


@transaction.atomic
def generate_stage_bracket(stage, *, seeded=True, third_place=False, random_seed=None):
    """Generate and persist a knockout bracket for a Stage.

    Draws from every Participant in the stage's Competition (a knockout
    stage that follows a group stage, drawing only the qualifiers, is a
    tournament-progression feature for a later phase — for now a knockout
    Stage uses the full competition participant pool, which is already the
    correct behavior for the common case of a single-stage knockout
    competition).
    """
    if stage.matches.exists():
        raise ScheduleAlreadyGeneratedError(_("This stage already has a generated bracket."))

    participants_qs = stage.competition.participants.filter(is_bye=False).order_by(
        F("seed").asc(nulls_last=True), "pk"
    )
    participant_ids = list(participants_qs.values_list("id", flat=True))
    if len(participant_ids) < 2:
        raise NotEnoughParticipantsError(_("A knockout stage needs at least two participants to generate a bracket."))

    bracket = generate_knockout_bracket(
        participant_ids, seeded=seeded, third_place=third_place, random_seed=random_seed
    )

    bye_participant = None
    if any(m.is_bye for m in bracket.matches):
        bye_participant = _get_or_create_bye_participant(stage.competition)

    matches = []
    for m in bracket.matches:
        a_id = m.participant_a
        b_id = m.participant_b
        if m.is_bye:
            if a_id is None:
                a_id = bye_participant.id
            if b_id is None:
                b_id = bye_participant.id
        matches.append(
            Match(
                competition_id=stage.competition_id,
                stage_id=stage.pk,
                group=None,
                round_number=m.round_number,
                bracket_slot=m.slot,
                participant_a_id=a_id,
                participant_b_id=b_id,
                is_bye=m.is_bye,
                is_third_place=m.is_third_place,
            )
        )
    Match.objects.bulk_create(matches)
    return bracket


@transaction.atomic
def clear_stage_bracket(stage):
    stage.matches.filter(group__isnull=True).delete()


def get_effective_rule(competition):
    """The competition's configured CompetitionRule, or an unsaved one
    holding just the model defaults, so scoring code never has to
    special-case "no rule configured yet"."""
    from apps.tournaments.models import CompetitionRule

    rule = getattr(competition, "rule", None)
    return rule if rule is not None else CompetitionRule(competition=competition)


def _points_to_win_for_set(rule, set_number):
    if rule.deciding_set_points and set_number == rule.best_of_sets:
        return rule.deciding_set_points
    return rule.points_per_set


@transaction.atomic
def record_set_score(match, set_number, participant_a_score, participant_b_score, *, allow_correction=False):
    """Validate and persist one set's score, then refresh the match result.

    Raises MatchAlreadyCompletedError if the match is already decided and
    allow_correction wasn't explicitly passed (CLAUDE.md: completed
    matches must not be silently overwritten) and InvalidSetNumberError if
    set_number is out of range for the competition's best-of-sets format.
    """
    if match.status == MatchStatus.COMPLETED and not allow_correction:
        raise MatchAlreadyCompletedError(
            _("This match is already completed. Explicitly correct it to change a score.")
        )

    rule = get_effective_rule(match.competition)
    if not (1 <= set_number <= rule.best_of_sets):
        raise InvalidSetNumberError(_("Set number must be between 1 and %(n)s.") % {"n": rule.best_of_sets})

    points_to_win = _points_to_win_for_set(rule, set_number)
    validate_set_score(
        participant_a_score, participant_b_score, points_to_win=points_to_win, win_by=rule.win_by, cap_at=rule.cap_at
    )

    MatchSet.objects.update_or_create(
        match=match,
        set_number=set_number,
        defaults={"participant_a_score": participant_a_score, "participant_b_score": participant_b_score},
    )
    _refresh_match_result(match, rule)


@transaction.atomic
def delete_set_score(match, set_number):
    match.sets.filter(set_number=set_number).delete()
    rule = get_effective_rule(match.competition)
    _refresh_match_result(match, rule)


def _refresh_match_result(match, rule):
    all_sets = list(match.sets.order_by("set_number").values_list("participant_a_score", "participant_b_score"))
    result = compute_match_result(all_sets, best_of_sets=rule.best_of_sets)

    was_completed = match.status == MatchStatus.COMPLETED
    if result.is_complete:
        match.winner_id = match.participant_a_id if result.winner == "a" else match.participant_b_id
        match.status = MatchStatus.COMPLETED
    else:
        match.winner_id = None
        match.status = MatchStatus.LIVE if all_sets else MatchStatus.SCHEDULED
    match.save(update_fields=["status", "winner"])

    if result.is_complete:
        _propagate_knockout_winner(match)
    elif was_completed:
        _clear_untouched_propagation(match)


def _next_bracket_match(match):
    if match.group_id is not None or match.bracket_slot is None:
        return None
    return Match.objects.filter(
        stage_id=match.stage_id,
        group__isnull=True,
        is_third_place=False,
        round_number=match.round_number + 1,
        bracket_slot=match.bracket_slot // 2,
    ).first()


def _propagate_knockout_winner(match):
    next_match = _next_bracket_match(match)
    if next_match is None:
        return
    field = "participant_a_id" if match.bracket_slot % 2 == 0 else "participant_b_id"
    setattr(next_match, field, match.winner_id)
    next_match.save(update_fields=[field])

    # If this was a semifinal, the loser feeds the third-place match (if any).
    total_rounds = Match.objects.filter(
        stage_id=match.stage_id, group__isnull=True, is_third_place=False
    ).aggregate(Max("round_number"))["round_number__max"]
    if match.round_number == total_rounds - 1:
        third_place_match = Match.objects.filter(stage_id=match.stage_id, is_third_place=True).first()
        if third_place_match is not None:
            loser_id = match.participant_b_id if match.winner_id == match.participant_a_id else match.participant_a_id
            field = "participant_a_id" if match.bracket_slot % 2 == 0 else "participant_b_id"
            setattr(third_place_match, field, loser_id)
            third_place_match.save(update_fields=[field])


def _clear_untouched_propagation(match):
    """A correction undid this match's completion. Roll back a winner it
    already fed forward, but only if that next match hasn't itself started
    (no sets recorded) — if it has, leave it alone: cascading a correction
    through already-played downstream matches isn't handled automatically.
    """
    next_match = _next_bracket_match(match)
    if next_match is None or next_match.sets.exists():
        return
    field = "participant_a_id" if match.bracket_slot % 2 == 0 else "participant_b_id"
    setattr(next_match, field, None)
    next_match.save(update_fields=[field])
