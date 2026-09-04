from django.db import connection
from django.shortcuts import render

from apps.players.models import DoublesPair, Player
from apps.teams.models import Team
from apps.tournaments.models import Tournament


def home(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        (postgres_version,) = cursor.fetchone()

    context = {
        "postgres_version": postgres_version,
        "tournament_count": Tournament.objects.count(),
        "player_count": Player.objects.count(),
        "team_count": Team.objects.count(),
        "pair_count": DoublesPair.objects.count(),
    }
    return render(request, "core/home.html", context)
