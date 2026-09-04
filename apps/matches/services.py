from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext_lazy as _

from apps.tournaments.services.knockout import generate_knockout_bracket
from apps.tournaments.services.round_robin import generate_round_robin

from .models import Match


class ScheduleAlreadyGeneratedError(Exception):
    pass


class NotEnoughParticipantsError(Exception):
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
