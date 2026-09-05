"""Aggregates the data behind the Referee / Scorekeeper dashboard
(CLAUDE.md section 25): a fast-entry-oriented view of what one match
official is working on right now, distinct from the Tournament Manager
dashboard (apps.tournaments.services.dashboard), which is about tournament-
wide progress rather than one person's queue of matches.
"""

from dataclasses import dataclass, field

from django.db.models import Q

from apps.tournaments.models import StaffRole, TournamentStaff

from .models import Match, MatchStatus
from .services import summarize_live_score

MATCH_ROLES = (
    StaffRole.TOURNAMENT_ADMIN,
    StaffRole.TOURNAMENT_MANAGER,
    StaffRole.REFEREE,
    StaffRole.SCOREKEEPER,
)
MATCH_LIST_LIMIT = 25


@dataclass
class ScorerDashboard:
    has_scoring_role: bool = False
    live_matches: list = field(default_factory=list)
    pending_matches: list = field(default_factory=list)
    unassigned_matches: list = field(default_factory=list)


def _scorable_tournament_ids(user):
    """None means "every tournament" (superuser); otherwise a concrete id list."""
    if user.is_superuser:
        return None
    return list(
        TournamentStaff.objects.filter(user=user, role__in=MATCH_ROLES)
        .values_list("tournament_id", flat=True)
        .distinct()
    )


def build_scorer_dashboard(user) -> ScorerDashboard:
    tournament_ids = _scorable_tournament_ids(user)
    dashboard = ScorerDashboard(has_scoring_role=user.is_superuser or bool(tournament_ids))
    if tournament_ids is not None and not tournament_ids:
        return dashboard

    matches_qs = Match.objects.select_related(
        "competition", "competition__tournament", "stage", "group", "participant_a", "participant_b"
    )
    if tournament_ids is not None:
        matches_qs = matches_qs.filter(competition__tournament_id__in=tournament_ids)

    assigned_to_me = matches_qs.filter(Q(referee=user) | Q(scorekeeper=user))
    dashboard.live_matches = list(
        assigned_to_me.filter(status=MatchStatus.LIVE)
        .prefetch_related("sets")
        .order_by("round_number", "pk")[:MATCH_LIST_LIMIT]
    )
    for match in dashboard.live_matches:
        match.live_score_summary = summarize_live_score(match)
    dashboard.pending_matches = list(
        assigned_to_me.filter(status__in=(MatchStatus.SCHEDULED, MatchStatus.READY)).order_by(
            "round_number", "pk"
        )[:MATCH_LIST_LIMIT]
    )
    dashboard.unassigned_matches = list(
        matches_qs.filter(
            status__in=(MatchStatus.SCHEDULED, MatchStatus.READY),
            referee__isnull=True,
            scorekeeper__isnull=True,
        )
        .exclude(participant_a__isnull=True)
        .exclude(participant_b__isnull=True)
        .order_by("round_number", "pk")[:MATCH_LIST_LIMIT]
    )
    return dashboard
