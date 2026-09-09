"""ITTF team-tie mechanics (CLAUDE.md section 9: team competitions).

A team-vs-team Match ("tie" in ITTF terms — see Match.parent_tie's
docstring) is decided by majority across 5 individual-player sub-matches,
in the standard order of play. Confirmed against the ITTF-ATTU 2025
Playing System document and ITTF Regulations §3.7.5.1-4:

    "Match order in team events are A vs X, B vs Y, C vs Z, A vs Y, B vs
    X. All individual matches of a team match shall be played in best of
    5 (five) games in all stages."

Each individual sub-match reuses this competition's own CompetitionRule
(best_of_sets etc.) unchanged — there's nothing team-specific about how
one game is scored, only about how the tie as a whole is decided.

Sub-match participants aren't scoped to one tie: each nominated player
gets one on-demand Individual Participant (Participant.is_tie_slot=True),
get-or-created the first time they're named in this competition and
reused for every later tie — so a player's Elo rating and any repeat
appearances accumulate the same way an ordinary Individual competition's
would (see apps.rankings.elo.sync_elo_ratings, which runs unmodified on
every sub-match through the normal record_set_score/_finalize_match
path).
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.tournaments.models import Participant, ParticipantType

from .models import TERMINAL_MATCH_STATUSES, Match, MatchStatus, TieLineup

# A-X, B-Y, C-Z, A-Y, B-X — index pairs into each side's 3-player lineup
# (lineup.players() == [player_a, player_b, player_c], i.e. [A, B, C] or
# [X, Y, Z] depending on which side).
ORDER_OF_PLAY = [(0, 0), (1, 1), (2, 2), (0, 1), (1, 0)]
WINS_REQUIRED = 3


class NotATieError(Exception):
    pass


class InvalidLineupError(Exception):
    pass


class LineupMissingError(Exception):
    pass


class TieAlreadyGeneratedError(Exception):
    pass


def _validate_tie(tie):
    if tie.parent_tie_id is not None:
        raise NotATieError(_("This match is itself an individual sub-match of a tie, not a tie."))
    if tie.competition.participant_type != ParticipantType.TEAM:
        raise NotATieError(_("Only a Team competition's matches are ties."))


def set_lineup(tie, team, players):
    """Nominate the 3 players — in order, ITTF's A/B/C — `team` (one of
    this tie's two sides) will field. Overwrites any lineup already set
    for this team on this tie, so a captain can revise it any time before
    generate_tie_matches locks it in by creating the sub-matches.

    Raises InvalidLineupError if team isn't one of the tie's two sides,
    the 3 players aren't distinct, or any of them isn't on team's roster.
    """
    _validate_tie(tie)
    if team.id not in (tie.participant_a.team_id, tie.participant_b.team_id):
        raise InvalidLineupError(_("This team isn't one of the two sides in this tie."))
    if len({p.id for p in players}) != 3:
        raise InvalidLineupError(_("Nominate exactly 3 different players."))

    roster_ids = set(team.members.values_list("id", flat=True))
    if not all(p.id in roster_ids for p in players):
        raise InvalidLineupError(_("Every nominated player must be on this team's roster."))

    lineup, _created = TieLineup.objects.update_or_create(
        tie=tie,
        team=team,
        defaults={"player_a": players[0], "player_b": players[1], "player_c": players[2]},
    )
    return lineup


def _get_or_create_slot_participant(competition, player):
    participant, _created = Participant.objects.get_or_create(
        competition=competition,
        individual_player=player,
        is_tie_slot=True,
        defaults={"participant_type": ParticipantType.INDIVIDUAL},
    )
    return participant


@transaction.atomic
def generate_tie_matches(tie):
    """Create this tie's 5 individual-player sub-matches from both sides'
    already-set lineups, in ITTF order of play.

    Sub-match participant_a is always drawn from tie.participant_a's
    lineup and participant_b from tie.participant_b's — fixing this
    orientation at creation is what lets every later result-counting
    (summarize_tie, standings) be a plain participant_a/participant_b
    comparison with no extra bookkeeping.

    Raises LineupMissingError if either side hasn't set a lineup yet, or
    TieAlreadyGeneratedError if this tie's sub-matches already exist.
    """
    _validate_tie(tie)
    if tie.tie_sub_matches.exists():
        raise TieAlreadyGeneratedError(_("This tie's matches have already been generated."))

    try:
        lineup_a = tie.lineups.get(team_id=tie.participant_a.team_id)
        lineup_b = tie.lineups.get(team_id=tie.participant_b.team_id)
    except TieLineup.DoesNotExist:
        raise LineupMissingError(_("Both teams must have a lineup set before generating this tie's matches."))

    players_a = lineup_a.players()
    players_b = lineup_b.players()

    matches = [
        Match(
            parent_tie=tie,
            tie_order=order,
            competition_id=tie.competition_id,
            stage_id=tie.stage_id,
            group_id=tie.group_id,
            round_number=tie.round_number,
            participant_a=_get_or_create_slot_participant(tie.competition, players_a[i]),
            participant_b=_get_or_create_slot_participant(tie.competition, players_b[j]),
        )
        for order, (i, j) in enumerate(ORDER_OF_PLAY, start=1)
    ]
    Match.objects.bulk_create(matches)
    return matches


@dataclass(frozen=True)
class TieSummary:
    wins_a: int
    wins_b: int
    games_won_a: int
    games_won_b: int
    points_scored_a: int
    points_scored_b: int


def summarize_tie(tie):
    """Aggregate this tie's sub-matches decided so far: individual
    matches won, total games (sets) won, and total points scored, for
    each side — the numbers both refresh_tie_result (decides the tie) and
    team-competition standings (ITTF §3.7.5.2's individual-match/games/
    points tie-break levels) are built from. An unplayed dead rubber
    contributes nothing to either side.
    """
    wins_a = wins_b = games_a = games_b = points_a = points_b = 0
    for sub in tie.tie_sub_matches.prefetch_related("sets"):
        sets = list(sub.sets.all())
        games_won_a = sum(1 for s in sets if s.participant_a_score > s.participant_b_score)
        games_won_b = sum(1 for s in sets if s.participant_b_score > s.participant_a_score)
        games_a += games_won_a
        games_b += games_won_b
        points_a += sum(s.participant_a_score for s in sets)
        points_b += sum(s.participant_b_score for s in sets)
        if sub.status in TERMINAL_MATCH_STATUSES:
            if sub.winner_id == sub.participant_a_id:
                wins_a += 1
            elif sub.winner_id == sub.participant_b_id:
                wins_b += 1
    return TieSummary(
        wins_a=wins_a, wins_b=wins_b, games_won_a=games_a, games_won_b=games_b,
        points_scored_a=points_a, points_scored_b=points_b,
    )


def refresh_tie_result(tie):
    """Recompute a tie's decided state from its sub-matches — called
    after any sub-match's result changes (matches/services.py hooks this
    into _refresh_match_result/_finalize_match).

    A no-op unless one side has now reached WINS_REQUIRED, and a no-op if
    the tie is already decided: a dead rubber played (or corrected) after
    the tie was already won doesn't reopen or change that decision.
    """
    if tie.status in TERMINAL_MATCH_STATUSES:
        return

    summary = summarize_tie(tie)
    if summary.wins_a >= WINS_REQUIRED:
        winner_id = tie.participant_a_id
    elif summary.wins_b >= WINS_REQUIRED:
        winner_id = tie.participant_b_id
    else:
        return

    from .services import _finalize_match  # local import: services.py calls back into this module

    _finalize_match(tie, winner_id=winner_id, status=MatchStatus.COMPLETED)
