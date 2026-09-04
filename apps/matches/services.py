from django.db import transaction
from django.utils.translation import gettext_lazy as _

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
