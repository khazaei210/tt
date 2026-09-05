from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _

from apps.core.csv_utils import csv_response
from apps.players.models import Player
from apps.tournaments.models import Competition, Tournament

from .services import build_player_statistics, build_tournament_report, iter_match_result_rows


def tournament_report(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    return render(
        request, "reports/tournament_report.html", {"tournament": tournament, "report": build_tournament_report(tournament)}
    )


def tournament_report_csv(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    report = build_tournament_report(tournament)
    header = [_("Competition"), _("Participant type"), _("Participants"), _("Matches decided"), _("Matches total"), _("Complete"), _("Final placements")]
    rows = []
    for row in report.competitions:
        placements = "; ".join(f"#{placement} {participant.display_name}" for placement, participant in row.placements)
        rows.append(
            [
                row.competition.name,
                row.competition.get_participant_type_display(),
                row.participant_count,
                row.matches_decided,
                row.matches_total,
                f"{row.completion_percent}%",
                placements,
            ]
        )
    return csv_response(f"tournament-{tournament.pk}-report.csv", header, rows)


def competition_results_csv(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    header = [_("Stage"), _("Group"), _("Round"), _("Participant A"), _("Participant B"), _("Status"), _("Winner"), _("Sets")]
    return csv_response(
        f"competition-{competition.pk}-results.csv", header, iter_match_result_rows(competition)
    )


def player_statistics(request, pk):
    player = get_object_or_404(Player, pk=pk)
    return render(request, "reports/player_statistics.html", {"player": player, "stats": build_player_statistics(player)})
