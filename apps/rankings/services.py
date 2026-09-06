"""Award global ranking points from a competition's final placements.

Tournament standings (apps.tournaments.services.standings) and match/bracket
results (apps.matches.services) already establish who finished where inside
one competition. This module's job is strictly the next step: turn that
result into ranking points for the players involved, tracked per
RankingCategory and independent of any single tournament (CLAUDE.md section
19). Placement determination and point-awarding are deliberately kept apart
so each can be tested and reasoned about on its own.
"""

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.tournaments.models import ParticipantType, StageFormat

from .models import PlayerRanking, RankingEvent, RankingCategory


class PlacementsNotAvailableError(Exception):
    pass


class RankingCategoryNotConfiguredError(Exception):
    pass


DEFAULT_RANKING_CATEGORY_NAME = "Overall"


def get_default_ranking_category():
    """The single global ranking category every competition is attached to
    automatically (Competition.save()), so Elo ratings and ranking points
    accumulate across every tournament with zero manager setup. A manager
    can still repoint a specific competition at a different category (or
    clear it) via the competition's edit form/admin if they want to keep it
    out of the global board — this only supplies the default."""
    category, _created = RankingCategory.objects.get_or_create(
        name=DEFAULT_RANKING_CATEGORY_NAME,
        defaults={"description": "Automatic global ranking across every competition."},
    )
    return category


def _placements_from_knockout(stage):
    """Placement dict for a completed knockout stage: {participant_id: placement}.

    Only the final's participants get a unique placement (1, 2). Every
    earlier round's losers are tied at the placement immediately after the
    number of participants who advanced past that round — e.g. in an
    8-bracket, both quarterfinal losers... no, both *semifinal* losers with
    no third-place match tie at 3, and all 4 quarterfinal losers tie at 5.
    This is the standard knockout convention: without a played consolation
    match, participants eliminated in the same round cannot be ranked
    against each other.
    """
    from apps.matches.models import MatchStatus

    matches = list(stage.matches.filter(group__isnull=True).select_related("participant_a", "participant_b"))
    if not matches:
        raise PlacementsNotAvailableError(_("This stage has no generated bracket yet."))

    real_matches = [m for m in matches if not m.is_bye]
    if any(m.status != MatchStatus.COMPLETED for m in real_matches):
        raise PlacementsNotAvailableError(_("This stage's bracket is not fully completed yet."))

    non_third_place = [m for m in matches if not m.is_third_place]
    total_rounds = max((m.round_number for m in non_third_place), default=0)
    final = next((m for m in non_third_place if m.round_number == total_rounds), None)
    if final is None or final.winner_id is None:
        raise PlacementsNotAvailableError(_("This stage's bracket is not fully completed yet."))

    placements = {final.winner_id: 1}
    runner_up_id = final.participant_a_id if final.winner_id == final.participant_b_id else final.participant_b_id
    placements[runner_up_id] = 2

    third_place_match = next((m for m in matches if m.is_third_place), None)
    if third_place_match is not None and third_place_match.winner_id is not None:
        placements[third_place_match.winner_id] = 3
        loser_id = (
            third_place_match.participant_a_id
            if third_place_match.winner_id == third_place_match.participant_b_id
            else third_place_match.participant_b_id
        )
        placements[loser_id] = 4
        semifinal_round = total_rounds - 1
    else:
        semifinal_round = total_rounds - 1
        for m in non_third_place:
            if m.round_number == semifinal_round and m.winner_id is not None:
                loser_id = m.participant_a_id if m.winner_id == m.participant_b_id else m.participant_b_id
                placements.setdefault(loser_id, 3)

    for m in non_third_place:
        if m.round_number >= semifinal_round or m.winner_id is None or m.is_bye:
            continue
        loser_id = m.participant_a_id if m.winner_id == m.participant_b_id else m.participant_b_id
        # Losers of round r (of total_rounds) tie at the placement right
        # after however many participants advanced past that round.
        placements.setdefault(loser_id, 2 ** (total_rounds - m.round_number) + 1)

    return placements


def determine_final_placements(competition):
    """{participant_id: placement} for a competition's final results.

    Uses the competition's last knockout stage if it has one (covers both
    pure knockout and group+knockout formats). Otherwise falls back to a
    single round-robin group's standings — a competition with several
    groups and no knockout stage has no single final ranking across groups,
    which is a real ambiguity this deliberately refuses to guess at.
    """
    knockout_stage = competition.stages.filter(stage_format=StageFormat.KNOCKOUT).order_by("-order").first()
    if knockout_stage is not None:
        return _placements_from_knockout(knockout_stage)

    stage = competition.stages.order_by("-order").first()
    if stage is None or stage.stage_format != StageFormat.ROUND_ROBIN:
        raise PlacementsNotAvailableError(_("This competition has no stage to determine placements from."))

    groups = list(stage.groups.all())
    if len(groups) != 1:
        raise PlacementsNotAvailableError(
            _("Final placements need either a knockout stage or a single round-robin group.")
        )

    from apps.matches.services import compute_group_standings

    rows = compute_group_standings(groups[0])
    if not rows:
        raise PlacementsNotAvailableError(_("This group has no completed matches yet."))
    return {row["participant"].id: row["rank"] for row in rows}


def players_for_participant(participant):
    """The Player(s) a Participant's ranking points should go to.

    Individual: the player. Doubles: both players in the pair, each in
    full — CLAUDE.md doesn't specify point-splitting, and full credit to
    both is the conventional doubles-ranking approach. Team participants
    are deliberately skipped: how team ranking points should be
    distributed to individual players isn't specified anywhere, and
    guessing would be exactly the kind of unstated business rule CLAUDE.md
    warns against (section 35) — team ranking can be added once that rule
    is defined.
    """
    if participant.participant_type == ParticipantType.INDIVIDUAL and participant.individual_player_id:
        return [participant.individual_player]
    if participant.participant_type == ParticipantType.DOUBLES and participant.doubles_pair_id:
        pair = participant.doubles_pair
        return [pair.player_one, pair.player_two]
    return []


@transaction.atomic
def award_ranking_points(competition, *, category=None):
    """Award ranking points for a competition's final placements.

    Idempotent per (player, category, competition): players already
    credited for this competition are skipped rather than re-awarded, so
    calling this again (e.g. after a late correction added a missing
    participant) only fills in gaps. Returns the list of RankingEvents
    created.
    """
    category = category or competition.ranking_category
    if category is None:
        raise RankingCategoryNotConfiguredError(
            _("This competition has no ranking category configured — set one before awarding points.")
        )

    placements = determine_final_placements(competition)
    scale = dict(category.points_scale.values_list("placement", "points"))

    participants = competition.participants.filter(is_bye=False).select_related(
        "individual_player", "doubles_pair__player_one", "doubles_pair__player_two"
    )

    created_events = []
    for participant in participants:
        placement = placements.get(participant.id)
        if placement is None:
            continue
        points = scale.get(placement, 0)

        for player in players_for_participant(participant):
            if RankingEvent.objects.filter(player=player, category=category, competition=competition).exists():
                continue

            ranking, _created = PlayerRanking.objects.get_or_create(player=player, category=category)
            points_before = ranking.points
            ranking.points = points_before + points
            ranking.tournaments_played += 1
            ranking.save(update_fields=["points", "tournaments_played", "updated_at"])

            created_events.append(
                RankingEvent.objects.create(
                    player=player,
                    category=category,
                    competition=competition,
                    placement=placement,
                    points_awarded=points,
                    points_before=points_before,
                    points_after=ranking.points,
                )
            )

    _recompute_ranks(category)
    return created_events


def _recompute_ranks(category):
    rankings = list(PlayerRanking.objects.filter(category=category).order_by("-points", "player_id"))
    for index, ranking in enumerate(rankings, start=1):
        if ranking.current_rank == index:
            continue
        ranking.previous_rank = ranking.current_rank
        ranking.current_rank = index
        ranking.save(update_fields=["previous_rank", "current_rank"])
