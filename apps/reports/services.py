"""Read-only aggregation for the Reports app (CLAUDE.md section 1/32):
a per-tournament progress/results summary and a per-player career record.

Deliberately has no models of its own — everything here is computed on
demand from Tournament/Competition/Match/Participant data that other apps
already own, the same way apps.tournaments.services.dashboard and
apps.matches.dashboard aggregate without owning their own tables.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from django.db.models import Q

from apps.matches.models import TERMINAL_MATCH_STATUSES, Match
from apps.rankings.services import PlacementsNotAvailableError, determine_final_placements
from apps.tournaments.models import Participant


@dataclass
class CompetitionReportRow:
    competition: Any
    participant_count: int
    matches_total: int
    matches_decided: int
    placements: list = field(default_factory=list)  # [(placement, participant), ...] top 3, best-effort

    @property
    def completion_percent(self) -> int:
        if not self.matches_total:
            return 0
        return round(100 * self.matches_decided / self.matches_total)


@dataclass
class TournamentReport:
    tournament: Any
    competitions: list = field(default_factory=list)


def build_tournament_report(tournament) -> TournamentReport:
    rows = []
    for competition in tournament.competitions.all().order_by("name"):
        participant_count = competition.participants.filter(is_bye=False).count()
        matches_qs = competition.matches.all()
        matches_total = matches_qs.count()
        matches_decided = matches_qs.filter(status__in=TERMINAL_MATCH_STATUSES).count()

        placements = []
        try:
            placement_by_participant_id = determine_final_placements(competition)
        except PlacementsNotAvailableError:
            placement_by_participant_id = None
        if placement_by_participant_id:
            top_ids = [pid for pid, place in placement_by_participant_id.items() if place <= 3]
            participants_by_id = {p.id: p for p in competition.participants.filter(id__in=top_ids)}
            placements = sorted(
                (
                    (placement_by_participant_id[pid], participant)
                    for pid, participant in participants_by_id.items()
                ),
                key=lambda row: row[0],
            )

        rows.append(
            CompetitionReportRow(
                competition=competition,
                participant_count=participant_count,
                matches_total=matches_total,
                matches_decided=matches_decided,
                placements=placements,
            )
        )
    return TournamentReport(tournament=tournament, competitions=rows)


@dataclass
class RecentMatchRow:
    match: Any
    opponent: Optional[Any]
    won: bool


@dataclass
class PlayerStatistics:
    player: Any
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    sets_won: int = 0
    sets_lost: int = 0
    points_scored: int = 0
    points_conceded: int = 0
    recent_matches: list = field(default_factory=list)

    @property
    def win_percentage(self) -> int:
        if not self.matches_played:
            return 0
        return round(100 * self.wins / self.matches_played)

    @property
    def set_difference(self) -> int:
        return self.sets_won - self.sets_lost

    @property
    def point_difference(self) -> int:
        return self.points_scored - self.points_conceded


RECENT_MATCH_LIMIT = 10


def build_player_statistics(player) -> PlayerStatistics:
    """A player's career record across every individual/doubles match they
    have played, decided matches only (in-progress matches don't count
    yet — same convention as tournament standings).

    Team matches are deliberately excluded: attributing a team result to
    one individual player's personal record isn't a rule CLAUDE.md
    specifies (same reasoning as apps.rankings.services skipping team
    ranking points).
    """
    participant_ids = list(
        Participant.objects.filter(
            Q(individual_player=player) | Q(doubles_pair__player_one=player) | Q(doubles_pair__player_two=player)
        ).values_list("id", flat=True)
    )
    stats = PlayerStatistics(player=player)
    if not participant_ids:
        return stats

    matches = (
        Match.objects.filter(
            Q(participant_a_id__in=participant_ids) | Q(participant_b_id__in=participant_ids),
            status__in=TERMINAL_MATCH_STATUSES,
            is_bye=False,
        )
        .select_related("competition", "competition__tournament", "participant_a", "participant_b")
        .prefetch_related("sets")
        .order_by("-pk")
    )

    for match in matches:
        is_a = match.participant_a_id in participant_ids
        if match.winner_id is None:
            continue
        stats.matches_played += 1
        won = match.winner_id == (match.participant_a_id if is_a else match.participant_b_id)
        if won:
            stats.wins += 1
        else:
            stats.losses += 1

        for match_set in match.sets.all():
            my_score = match_set.participant_a_score if is_a else match_set.participant_b_score
            opp_score = match_set.participant_b_score if is_a else match_set.participant_a_score
            stats.points_scored += my_score
            stats.points_conceded += opp_score
            if my_score > opp_score:
                stats.sets_won += 1
            elif opp_score > my_score:
                stats.sets_lost += 1

        if len(stats.recent_matches) < RECENT_MATCH_LIMIT:
            opponent = match.participant_b if is_a else match.participant_a
            stats.recent_matches.append(RecentMatchRow(match=match, opponent=opponent, won=won))

    return stats
