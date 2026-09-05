from django.shortcuts import get_object_or_404, render

from apps.players.models import Player
from apps.tournaments.models import Tournament

from .services import build_player_statistics, build_tournament_report


def tournament_report(request, pk):
    tournament = get_object_or_404(Tournament, pk=pk)
    return render(
        request, "reports/tournament_report.html", {"tournament": tournament, "report": build_tournament_report(tournament)}
    )


def player_statistics(request, pk):
    player = get_object_or_404(Player, pk=pk)
    return render(request, "reports/player_statistics.html", {"player": player, "stats": build_player_statistics(player)})
