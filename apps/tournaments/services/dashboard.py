"""Aggregates the data behind the Tournament Manager dashboard (CLAUDE.md
section 25): the tournaments a user manages, their progress, and the
live/upcoming/completed matches within them.

Two items from that section's list are deliberately not produced here:

- "Table utilization" — there is no Table/Venue model yet (that's Phase
  10 in the roadmap); nothing to aggregate.
- "Current standings" — standings are per-Group (see
  tournaments.services.standings) and can be numerous within one
  tournament. Computing every group's table on every dashboard load
  would be a dashboard-query performance trap (CLAUDE.md section 32
  calls this out explicitly), for a summary view where a progress bar
  already tells the manager what needs attention. Full standings stay
  one click away on each group's own page.

"Upcoming" here means "not yet started" (status SCHEDULED/READY) rather
than a chronological queue — Match has no scheduled_time field yet.
"""

from dataclasses import dataclass, field

from django.db.models import Case, Count, Q, When

from apps.matches.models import Match, MatchStatus
from apps.matches.services import summarize_live_score

from ..models import StaffRole, Tournament, TournamentStatus, TournamentStaff

MANAGEMENT_ROLES = (StaffRole.TOURNAMENT_ADMIN, StaffRole.TOURNAMENT_MANAGER)
ACTIVE_STATUSES = (TournamentStatus.UPCOMING, TournamentStatus.ONGOING)
MATCH_LIST_LIMIT = 15


@dataclass
class TournamentProgress:
    tournament: Tournament
    competition_count: int
    participant_count: int
    total_matches: int
    completed_matches: int

    @property
    def progress_percent(self) -> int:
        if not self.total_matches:
            return 0
        return round(100 * self.completed_matches / self.total_matches)


@dataclass
class ManagerDashboard:
    tournaments: list = field(default_factory=list)
    live_matches: list = field(default_factory=list)
    upcoming_matches: list = field(default_factory=list)
    recent_completed_matches: list = field(default_factory=list)

    @property
    def active_tournament_count(self) -> int:
        return sum(1 for t in self.tournaments if t.tournament.status in ACTIVE_STATUSES)

    @property
    def total_participants(self) -> int:
        return sum(t.participant_count for t in self.tournaments)


def _managed_tournament_ids(user):
    """None means "every tournament" (superuser); otherwise a concrete id list."""
    if user.is_superuser:
        return None
    return list(
        TournamentStaff.objects.filter(user=user, role__in=MANAGEMENT_ROLES)
        .values_list("tournament_id", flat=True)
        .distinct()
    )


def build_manager_dashboard(user) -> ManagerDashboard:
    tournament_ids = _managed_tournament_ids(user)
    if tournament_ids is not None and not tournament_ids:
        return ManagerDashboard()

    tournaments_qs = Tournament.objects.all()
    matches_qs = Match.objects.select_related(
        "competition", "competition__tournament", "stage", "group", "participant_a", "participant_b"
    )
    if tournament_ids is not None:
        tournaments_qs = tournaments_qs.filter(pk__in=tournament_ids)
        matches_qs = matches_qs.filter(competition__tournament_id__in=tournament_ids)

    tournaments_qs = tournaments_qs.annotate(
        competition_count=Count("competitions", distinct=True),
        participant_count=Count(
            "competitions__participants",
            filter=Q(competitions__participants__is_bye=False),
            distinct=True,
        ),
        total_match_count=Count("competitions__matches", distinct=True),
        completed_match_count=Count(
            "competitions__matches",
            filter=Q(competitions__matches__status=MatchStatus.COMPLETED),
            distinct=True,
        ),
    ).order_by(
        Case(
            When(status=TournamentStatus.ONGOING, then=0),
            When(status=TournamentStatus.UPCOMING, then=1),
            When(status=TournamentStatus.DRAFT, then=2),
            default=3,
        ),
        "-start_date",
        "name",
    )

    tournaments = [
        TournamentProgress(
            tournament=t,
            competition_count=t.competition_count,
            participant_count=t.participant_count,
            total_matches=t.total_match_count,
            completed_matches=t.completed_match_count,
        )
        for t in tournaments_qs
    ]

    live_matches = list(
        matches_qs.filter(status=MatchStatus.LIVE).prefetch_related("sets")[:MATCH_LIST_LIMIT]
    )
    for match in live_matches:
        match.live_score_summary = summarize_live_score(match)

    return ManagerDashboard(
        tournaments=tournaments,
        live_matches=live_matches,
        upcoming_matches=list(
            matches_qs.filter(status__in=(MatchStatus.SCHEDULED, MatchStatus.READY)).order_by(
                "round_number", "pk"
            )[:MATCH_LIST_LIMIT]
        ),
        recent_completed_matches=list(
            matches_qs.filter(status=MatchStatus.COMPLETED).order_by("-pk")[:MATCH_LIST_LIMIT]
        ),
    )
