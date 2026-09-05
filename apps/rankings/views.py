from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.tournaments.models import Competition
from apps.tournaments.permissions import tournament_manager_required

from .models import RankingCategory
from .services import PlacementsNotAvailableError, RankingCategoryNotConfiguredError, award_ranking_points


def category_list(request):
    categories = RankingCategory.objects.all()
    return render(request, "rankings/category_list.html", {"categories": categories})


def category_detail(request, pk):
    category = get_object_or_404(RankingCategory, pk=pk)
    rankings = category.player_rankings.select_related("player").order_by("current_rank", "-points")
    return render(request, "rankings/category_detail.html", {"category": category, "rankings": rankings})


@login_required
def my_rankings(request):
    player = getattr(request.user, "player_profile", None)
    rankings = player.rankings.select_related("category").order_by("category__name") if player else []
    events = player.ranking_events.select_related("category", "competition")[:20] if player else []
    return render(request, "rankings/my_rankings.html", {"player": player, "rankings": rankings, "events": events})


def _tournament_from_competition_pk(request, pk, **kwargs):
    return get_object_or_404(Competition, pk=pk).tournament


@tournament_manager_required(_tournament_from_competition_pk)
def award_points(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=pk)
    try:
        events = award_ranking_points(competition)
    except (PlacementsNotAvailableError, RankingCategoryNotConfiguredError) as exc:
        messages.error(request, str(exc))
    else:
        if events:
            messages.success(request, _("Awarded ranking points to %(n)s player(s).") % {"n": len(events)})
        else:
            messages.info(request, _("No new ranking points to award — everyone eligible was already credited."))
    return redirect("tournaments:competition_detail", pk=competition.pk)
