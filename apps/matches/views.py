from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.generic import DetailView

from apps.tournaments.permissions import can_score_matches, match_scorer_required

from .dashboard import build_scorer_dashboard
from .forms import SetScoreForm
from .models import TERMINAL_MATCH_STATUSES, Match
from .scoring import ScoreValidationError
from .services import (
    InvalidOfficialRoleError,
    InvalidSetNumberError,
    InvalidWinnerError,
    MatchAlreadyCompletedError,
    claim_match,
    delete_set_score,
    get_effective_rule,
    record_default,
    record_retirement,
    record_set_score,
    record_walkover,
    start_match,
)


def _tournament_from_match_pk(request, pk, **kwargs):
    return get_object_or_404(Match, pk=pk).competition.tournament


SPECIAL_RESULTS = [
    ("walkover", "matches:walkover", _("Walkover"), _("Record a walkover for the chosen side?")),
    ("retire", "matches:retire", _("Retirement"), _("Record a retirement — the other side wins?")),
    ("default", "matches:default", _("Default"), _("Record a default for the chosen side?")),
]


def _scoreboard_context(request, match):
    rule = get_effective_rule(match.competition)
    sets = list(match.sets.order_by("set_number"))
    next_set_number = len(sets) + 1
    return {
        "match": match,
        "rule": rule,
        "sets": sets,
        "next_set_number": next_set_number if next_set_number <= rule.best_of_sets else None,
        "can_score": can_score_matches(request.user, match.competition.tournament),
        "is_decided": match.status in TERMINAL_MATCH_STATUSES,
        "special_results": SPECIAL_RESULTS,
        "corrections": match.corrections.select_related("performed_by")[:20],
    }


class MatchDetailView(DetailView):
    model = Match
    template_name = "matches/match_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_scoreboard_context(self.request, self.object))
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
                performed_by=request.user,
            )
        except (ScoreValidationError, MatchAlreadyCompletedError, InvalidSetNumberError) as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, _("Please enter a valid score for both sides."))

    if request.htmx:
        match.refresh_from_db()
        return render(request, "matches/_scoreboard.html", _scoreboard_context(request, match))
    return redirect("matches:detail", pk=match.pk)


@match_scorer_required(_tournament_from_match_pk)
def match_set_delete(request, pk, set_number):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    match = get_object_or_404(Match, pk=pk)
    try:
        delete_set_score(
            match,
            set_number,
            allow_correction=request.POST.get("allow_correction") == "1",
            performed_by=request.user,
        )
    except MatchAlreadyCompletedError as exc:
        messages.error(request, str(exc))

    if request.htmx:
        match.refresh_from_db()
        return render(request, "matches/_scoreboard.html", _scoreboard_context(request, match))
    return redirect("matches:detail", pk=match.pk)


@match_scorer_required(_tournament_from_match_pk)
def match_start(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    match = get_object_or_404(Match, pk=pk)
    try:
        start_match(match)
    except MatchAlreadyCompletedError as exc:
        messages.error(request, str(exc))

    if request.htmx:
        return render(request, "matches/_scoreboard.html", _scoreboard_context(request, match))
    return redirect("matches:detail", pk=match.pk)


def _winner_id_from_request(request, match):
    side = request.POST.get("winner")
    if side == "a":
        return match.participant_a_id
    if side == "b":
        return match.participant_b_id
    return None


@match_scorer_required(_tournament_from_match_pk)
def match_walkover(request, pk):
    return _record_special_result(request, pk, record_walkover, _("Walkover recorded."))


@match_scorer_required(_tournament_from_match_pk)
def match_retire(request, pk):
    return _record_special_result(request, pk, record_retirement, _("Retirement recorded."))


@match_scorer_required(_tournament_from_match_pk)
def match_default(request, pk):
    return _record_special_result(request, pk, record_default, _("Default recorded."))


def _record_special_result(request, pk, record_func, success_message):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    match = get_object_or_404(Match, pk=pk)
    winner_id = _winner_id_from_request(request, match)
    if winner_id is None:
        messages.error(request, _("Choose which participant won."))
    else:
        try:
            record_func(
                match,
                winner_id,
                allow_correction=request.POST.get("allow_correction") == "1",
                performed_by=request.user,
            )
        except (InvalidWinnerError, MatchAlreadyCompletedError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, success_message)

    if request.htmx:
        match.refresh_from_db()
        return render(request, "matches/_scoreboard.html", _scoreboard_context(request, match))
    return redirect("matches:detail", pk=match.pk)


@match_scorer_required(_tournament_from_match_pk)
def match_claim(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    match = get_object_or_404(Match, pk=pk)
    role = request.POST.get("role")
    try:
        claim_match(match, request.user, role)
    except InvalidOfficialRoleError as exc:
        messages.error(request, str(exc))

    if request.htmx:
        return render(request, "matches/_scoreboard.html", _scoreboard_context(request, match))
    return redirect("matches:detail", pk=match.pk)


@login_required
def scorer_dashboard(request):
    """The Referee / Scorekeeper dashboard (CLAUDE.md section 25): matches
    assigned to this user (live, then pending) plus unassigned matches in
    tournaments where they hold a scoring role, ready to be picked up.
    """
    return render(request, "matches/scorer_dashboard.html", {"dashboard": build_scorer_dashboard(request.user)})
