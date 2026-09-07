"""Aggregates the data behind a player's own dashboard (CLAUDE.md section
25: upcoming matches, match history, tournament participation, ranking).

Career/decided-match history already exists as
apps.reports.services.build_player_statistics and ranking data as
apps.rankings.views.my_rankings — this only adds the piece neither of
those cover, matches still in progress, and the list of tournaments the
player is registered in, the same way apps.matches.dashboard and
apps.tournaments.services.dashboard aggregate without owning their own
tables.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from apps.matches.models import Match, MatchStatus
from apps.tournaments.models import Participant, Tournament

UPCOMING_STATUSES = (MatchStatus.SCHEDULED, MatchStatus.READY, MatchStatus.LIVE)
UPCOMING_MATCH_LIMIT = 10


@dataclass
class PlayerDashboard:
    player: object = None
    upcoming_matches: list = field(default_factory=list)
    tournaments: list = field(default_factory=list)


def _participant_ids_for(player):
    return list(
        Participant.objects.filter(
            Q(individual_player=player)
            | Q(doubles_pair__player_one=player)
            | Q(doubles_pair__player_two=player)
            | Q(team__memberships__player=player, team__memberships__is_active=True)
        ).values_list("id", flat=True)
    )


def build_player_dashboard(player) -> PlayerDashboard:
    dashboard = PlayerDashboard(player=player)
    if player is None:
        return dashboard

    participant_ids = _participant_ids_for(player)
    if not participant_ids:
        return dashboard

    dashboard.upcoming_matches = list(
        Match.objects.filter(
            Q(participant_a_id__in=participant_ids) | Q(participant_b_id__in=participant_ids),
            status__in=UPCOMING_STATUSES,
        )
        .select_related("competition", "competition__tournament", "participant_a", "participant_b")
        .order_by("start_time", "round_number", "pk")[:UPCOMING_MATCH_LIMIT]
    )
    dashboard.tournaments = list(
        Tournament.objects.filter(competitions__participants__id__in=participant_ids)
        .distinct()
        .order_by("-start_date", "name")
    )
    return dashboard
