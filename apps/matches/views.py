from django.contrib import messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.generic import DetailView

from apps.tournaments.permissions import can_score_matches, match_scorer_required

from .forms import SetScoreForm
from .models import Match
from .scoring import ScoreValidationError
from .services import (
    InvalidSetNumberError,
    MatchAlreadyCompletedError,
    delete_set_score,
    get_effective_rule,
    record_set_score,
)


def _tournament_from_match_pk(request, pk, **kwargs):
    return get_object_or_404(Match, pk=pk).competition.tournament


class MatchDetailView(DetailView):
    model = Match
    template_name = "matches/match_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        match = self.object
        rule = get_effective_rule(match.competition)
        sets = list(match.sets.order_by("set_number"))
        context["rule"] = rule
        context["sets"] = sets
        next_set_number = len(sets) + 1
        context["next_set_number"] = next_set_number if next_set_number <= rule.best_of_sets else None
        context["set_form"] = SetScoreForm()
        context["can_score"] = can_score_matches(self.request.user, match.competition.tournament)
        return context


@match_scorer_required(_tournament_from_match_pk)
def match_set_save(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    match = get_object_or_404(Match, pk=pk)
    form = SetScoreForm(request.POST)
    try:
        set_number = int(request.POST.get("set_number", 0))
    except (TypeError, ValueError):
        set_number = 0

    if form.is_valid():
        try:
            record_set_score(
                match,
                set_number,
                form.cleaned_data["participant_a_score"],
                form.cleaned_data["participant_b_score"],
                allow_correction=request.POST.get("allow_correction") == "1",
            )
        except (ScoreValidationError, MatchAlreadyCompletedError, InvalidSetNumberError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, _("Please enter a valid score for both sides."))
    return redirect("matches:detail", pk=match.pk)


@match_scorer_required(_tournament_from_match_pk)
def match_set_delete(request, pk, set_number):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    match = get_object_or_404(Match, pk=pk)
    delete_set_score(match, set_number)
    return redirect("matches:detail", pk=match.pk)
