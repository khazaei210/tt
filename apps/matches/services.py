from dataclasses import dataclass

from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.tournaments.services.knockout import generate_knockout_bracket
from apps.tournaments.services.round_robin import generate_round_robin
from apps.tournaments.services.standings import MatchRecord, compute_standings

from .models import Match, MatchCorrection, MatchCorrectionAction, MatchSet, MatchStatus, TERMINAL_MATCH_STATUSES
from .scoring import compute_match_result, validate_set_score


class ScheduleAlreadyGeneratedError(Exception):
    pass


class NotEnoughParticipantsError(Exception):
    pass


class MatchAlreadyCompletedError(Exception):
    pass


class InvalidSetNumberError(Exception):
    pass


class StageNotCompleteError(Exception):
    pass


class QualifiersNotConfiguredError(Exception):
    pass


class NoKnockoutStageError(Exception):
    pass


class InvalidWinnerError(Exception):
    pass


class InvalidOfficialRoleError(Exception):
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
def generate_stage_bracket(stage, *, seeded=True, third_place=False, random_seed=None, participant_ids=None):
    """Generate and persist a knockout bracket for a Stage.

    By default, draws from every Participant in the stage's Competition,
    ordered by their competition-wide seed — the correct behavior for a
    single-stage knockout competition. Pass an explicit participant_ids
    (already in the desired seed order) to bracket a specific subset
    instead — used by advance_to_next_stage() to bracket only a preceding
    group stage's qualifiers, not the whole competition.
    """
    if stage.matches.exists():
        raise ScheduleAlreadyGeneratedError(_("This stage already has a generated bracket."))

    if participant_ids is None:
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


@transaction.atomic
def advance_to_next_stage(source_stage):
    """Take a completed round-robin stage's group qualifiers and bracket
    them into its competition's next (knockout) stage.

    Seeding interleaves by group rank (every group's winner first, then
    every group's runner-up, and so on) rather than group order, so seed 1
    and 2 are two different groups' winners — the standard "top seeds can't
    meet early" property from generate_knockout_bracket's seed_positions()
    only holds if seed order doesn't cluster group-mates together.

    Raises StageNotCompleteError if any group still has unplayed matches,
    QualifiersNotConfiguredError if source_stage.qualifiers_per_group isn't
    set, and NoKnockoutStageError if the competition has no knockout stage
    right after this one.
    """
    from apps.tournaments.models import StageFormat

    if source_stage.stage_format != StageFormat.ROUND_ROBIN:
        raise NoKnockoutStageError(_("Only a round-robin stage can advance qualifiers to a knockout stage."))
    if not source_stage.qualifiers_per_group:
        raise QualifiersNotConfiguredError(_("Set how many qualifiers advance per group before advancing."))

    groups = list(source_stage.groups.order_by("order"))
    if not groups:
        raise NotEnoughParticipantsError(_("This stage has no groups to qualify participants from."))
    if source_stage.matches.exclude(status=MatchStatus.COMPLETED).exists():
        raise StageNotCompleteError(_("Every match in this stage must be completed before advancing qualifiers."))

    next_stage = source_stage.competition.stages.filter(
        order=source_stage.order + 1, stage_format=StageFormat.KNOCKOUT
    ).first()
    if next_stage is None:
        raise NoKnockoutStageError(_("This competition has no knockout stage immediately after this one."))

    per_group_qualifiers = [
        [row["participant"].id for row in compute_group_standings(group)[: source_stage.qualifiers_per_group]]
        for group in groups
    ]
    max_qualifiers = max((len(q) for q in per_group_qualifiers), default=0)
    seeded_ids = [
        participant_id
        for rank_index in range(max_qualifiers)
        for group_qualifiers in per_group_qualifiers
        if rank_index < len(group_qualifiers)
        for participant_id in [group_qualifiers[rank_index]]
    ]

    return generate_stage_bracket(next_stage, seeded=True, participant_ids=seeded_ids)


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


def _describe_result(match):
    """Short human-readable summary of a match's decided state, for
    MatchCorrection's previous_value/new_value (CLAUDE.md section 33: keep
    corrections traceable without inventing a bespoke structured diff)."""
    if match.status not in TERMINAL_MATCH_STATUSES:
        return str(_("Not yet decided"))
    winner_name = match.winner.display_name if match.winner_id else "—"
    return f"{match.get_status_display()} — {_('winner')}: {winner_name}"


@transaction.atomic
def record_set_score(
    match, set_number, participant_a_score, participant_b_score, *, allow_correction=False, performed_by=None
):
    """Validate and persist one set's score, then refresh the match result.

    Raises MatchAlreadyCompletedError if the match is already decided and
    allow_correction wasn't explicitly passed (CLAUDE.md: completed
    matches must not be silently overwritten) and InvalidSetNumberError if
    set_number is out of range for the competition's best-of-sets format.

    Overwriting an already-recorded set's numbers, or correcting a decided
    match, logs a MatchCorrection (performed_by is who did it, for the
    audit trail — CLAUDE.md section 33).
    """
    was_terminal = match.status in TERMINAL_MATCH_STATUSES
    if was_terminal and not allow_correction:
        raise MatchAlreadyCompletedError(
            _("This match is already decided. Explicitly correct it to change a score.")
        )

    rule = get_effective_rule(match.competition)
    if not (1 <= set_number <= rule.best_of_sets):
        raise InvalidSetNumberError(_("Set number must be between 1 and %(n)s.") % {"n": rule.best_of_sets})

    points_to_win = _points_to_win_for_set(rule, set_number)
    validate_set_score(
        participant_a_score, participant_b_score, points_to_win=points_to_win, win_by=rule.win_by, cap_at=rule.cap_at
    )

    previous_result = _describe_result(match) if was_terminal else None
    existing_set = match.sets.filter(set_number=set_number).first()

    MatchSet.objects.update_or_create(
        match=match,
        set_number=set_number,
        defaults={"participant_a_score": participant_a_score, "participant_b_score": participant_b_score},
    )
    _refresh_match_result(match, rule)

    if existing_set is not None and (
        existing_set.participant_a_score != participant_a_score
        or existing_set.participant_b_score != participant_b_score
    ):
        MatchCorrection.objects.create(
            match=match,
            action=MatchCorrectionAction.SET_SCORE_CHANGED,
            set_number=set_number,
            previous_value=f"{existing_set.participant_a_score}-{existing_set.participant_b_score}",
            new_value=f"{participant_a_score}-{participant_b_score}",
            performed_by=performed_by,
        )
    if was_terminal:
        MatchCorrection.objects.create(
            match=match,
            action=MatchCorrectionAction.RESULT_CORRECTED,
            previous_value=previous_result,
            new_value=_describe_result(match),
            performed_by=performed_by,
        )


@transaction.atomic
def delete_set_score(match, set_number, *, allow_correction=False, performed_by=None):
    """Remove one set's recorded score and refresh the match result.

    Raises MatchAlreadyCompletedError if the match is already decided and
    allow_correction wasn't explicitly passed — deleting a recorded score
    from a decided match is exactly the kind of silent overwrite CLAUDE.md
    section 33 rules out, same as record_set_score's guard.
    """
    was_terminal = match.status in TERMINAL_MATCH_STATUSES
    if was_terminal and not allow_correction:
        raise MatchAlreadyCompletedError(
            _("This match is already decided. Explicitly correct it to delete a recorded score.")
        )

    existing_set = match.sets.filter(set_number=set_number).first()
    if existing_set is None:
        return

    previous_result = _describe_result(match) if was_terminal else None
    existing_set.delete()
    rule = get_effective_rule(match.competition)
    _refresh_match_result(match, rule)

    MatchCorrection.objects.create(
        match=match,
        action=MatchCorrectionAction.SET_SCORE_DELETED,
        set_number=set_number,
        previous_value=f"{existing_set.participant_a_score}-{existing_set.participant_b_score}",
        new_value="",
        performed_by=performed_by,
    )
    if was_terminal:
        MatchCorrection.objects.create(
            match=match,
            action=MatchCorrectionAction.RESULT_CORRECTED,
            previous_value=previous_result,
            new_value=_describe_result(match),
            performed_by=performed_by,
        )


def _refresh_match_result(match, rule):
    all_sets = list(match.sets.order_by("set_number").values_list("participant_a_score", "participant_b_score"))
    result = compute_match_result(all_sets, best_of_sets=rule.best_of_sets)

    was_decided = match.status in TERMINAL_MATCH_STATUSES
    if result.is_complete:
        match.winner_id = match.participant_a_id if result.winner == "a" else match.participant_b_id
        match.status = MatchStatus.COMPLETED
        match.end_time = match.end_time or timezone.now()
    else:
        match.winner_id = None
        match.status = MatchStatus.LIVE if all_sets else MatchStatus.SCHEDULED
        match.end_time = None
    match.save(update_fields=["status", "winner", "end_time"])

    if result.is_complete:
        _propagate_knockout_winner(match)
    elif was_decided:
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


@transaction.atomic
def start_match(match):
    """Mark a match LIVE and stamp its start time (once).

    A no-op if the match is already LIVE (e.g. the referee's page was
    reloaded); raises MatchAlreadyCompletedError if the match is already
    decided — you can't "start" a match that's over.
    """
    if match.status in TERMINAL_MATCH_STATUSES:
        raise MatchAlreadyCompletedError(_("This match is already decided."))
    if match.status == MatchStatus.LIVE:
        return match
    match.status = MatchStatus.LIVE
    match.start_time = match.start_time or timezone.now()
    match.save(update_fields=["status", "start_time"])
    return match


def _validate_winner(match, winner_id):
    if winner_id not in (match.participant_a_id, match.participant_b_id):
        raise InvalidWinnerError(_("The winner must be one of this match's two participants."))


@transaction.atomic
def _finalize_match(match, *, winner_id, status, allow_correction=False, performed_by=None):
    was_terminal = match.status in TERMINAL_MATCH_STATUSES
    if was_terminal and not allow_correction:
        raise MatchAlreadyCompletedError(
            _("This match is already decided. Explicitly correct it to change the result.")
        )
    _validate_winner(match, winner_id)
    previous_result = _describe_result(match) if was_terminal else None

    match.winner_id = winner_id
    match.status = status
    match.end_time = match.end_time or timezone.now()
    match.save(update_fields=["winner", "status", "end_time"])
    _propagate_knockout_winner(match)

    if was_terminal:
        MatchCorrection.objects.create(
            match=match,
            action=MatchCorrectionAction.RESULT_CORRECTED,
            previous_value=previous_result,
            new_value=_describe_result(match),
            performed_by=performed_by,
        )
    return match


def record_walkover(match, winner_id, *, allow_correction=False, performed_by=None):
    """The opponent didn't show up — winner_id advances with no sets played."""
    return _finalize_match(
        match, winner_id=winner_id, status=MatchStatus.WALKOVER, allow_correction=allow_correction,
        performed_by=performed_by,
    )


def record_retirement(match, winner_id, *, allow_correction=False, performed_by=None):
    """A participant retired mid-match — winner_id wins; any sets already
    recorded are left in place as a record of how far the match got."""
    return _finalize_match(
        match, winner_id=winner_id, status=MatchStatus.RETIRED, allow_correction=allow_correction,
        performed_by=performed_by,
    )


def record_default(match, winner_id, *, allow_correction=False, performed_by=None):
    """A participant was disqualified/defaulted — winner_id wins."""
    return _finalize_match(
        match, winner_id=winner_id, status=MatchStatus.DEFAULT, allow_correction=allow_correction,
        performed_by=performed_by,
    )


def claim_match(match, user, role):
    """Assign user as this match's referee or scorekeeper.

    Simply overwrites any existing assignment — reassigning isn't a
    protected action the way a scored result is; whoever has scoring
    access to this match can pick it up or hand it to someone else.
    """
    if role == "referee":
        match.referee = user
        match.save(update_fields=["referee"])
    elif role == "scorekeeper":
        match.scorekeeper = user
        match.save(update_fields=["scorekeeper"])
    else:
        raise InvalidOfficialRoleError(_('role must be "referee" or "scorekeeper".'))
    return match


@dataclass(frozen=True)
class LiveScoreSummary:
    sets_score: str
    last_set_score: str


def summarize_live_score(match):
    """A compact "sets won so far / most recent set" summary for a match
    row on a dashboard, or None if no set has been recorded yet.

    There's no point-by-point live tracking in this system — only
    completed sets are ever stored (record_set_score) — so "the current
    score" for a match still in progress is exactly this: how many sets
    each side has won, and the last set actually recorded.

    Expects match.sets to already be prefetched by the caller; called
    once per row on a dashboard listing, so an extra query per match
    here would be an N+1 (CLAUDE.md section 32).
    """
    sets = list(match.sets.all())
    if not sets:
        return None
    sets_won_a = sum(1 for s in sets if s.participant_a_score > s.participant_b_score)
    sets_won_b = sum(1 for s in sets if s.participant_b_score > s.participant_a_score)
    last = sets[-1]
    return LiveScoreSummary(
        sets_score=f"{sets_won_a}-{sets_won_b}",
        last_set_score=f"{last.participant_a_score}-{last.participant_b_score}",
    )


def compute_group_standings(group):
    """Standings for a round-robin Group, computed from its completed
    matches only (in-progress or unplayed matches don't count yet).

    Returns a list of dicts (rank, participant, played, wins, losses,
    match_points, sets_won, sets_lost, set_difference, points_scored,
    points_conceded, point_difference) ordered best-first, using the
    default tie-break sequence (head-to-head, set difference, point
    difference, points scored) — see
    apps.tournaments.services.standings for the tie-break logic itself.
    """
    from apps.tournaments.models import Participant

    participant_ids = list(group.group_participants.values_list("participant_id", flat=True))
    completed_matches = Match.objects.filter(group=group, status=MatchStatus.COMPLETED).prefetch_related("sets")

    match_records = []
    for m in completed_matches:
        sets = list(m.sets.all())
        match_records.append(
            MatchRecord(
                participant_a=m.participant_a_id,
                participant_b=m.participant_b_id,
                sets_won_a=sum(1 for s in sets if s.participant_a_score > s.participant_b_score),
                sets_won_b=sum(1 for s in sets if s.participant_b_score > s.participant_a_score),
                points_scored_a=sum(s.participant_a_score for s in sets),
                points_scored_b=sum(s.participant_b_score for s in sets),
            )
        )

    rows = compute_standings(participant_ids, match_records)
    participants_by_id = {p.id: p for p in Participant.objects.filter(id__in=participant_ids)}

    return [
        {
            "rank": row.rank,
            "participant": participants_by_id[row.participant],
            "played": row.played,
            "wins": row.wins,
            "losses": row.losses,
            "match_points": row.match_points,
            "sets_won": row.sets_won,
            "sets_lost": row.sets_lost,
            "set_difference": row.set_difference,
            "points_scored": row.points_scored,
            "points_conceded": row.points_conceded,
            "point_difference": row.point_difference,
        }
        for row in rows
    ]
