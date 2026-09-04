from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.matches.services import (
    NotEnoughParticipantsError,
    ScheduleAlreadyGeneratedError,
    clear_group_schedule,
    clear_stage_bracket,
    compute_group_standings,
    generate_group_schedule,
    generate_stage_bracket,
)

from .forms import (
    CompetitionForm,
    CompetitionRuleForm,
    GroupForm,
    GroupParticipantForm,
    ParticipantForm,
    StageForm,
    TournamentForm,
)
from .models import Competition, CompetitionRule, Group, GroupParticipant, Participant, Stage, StageFormat, Tournament


class TournamentListView(ListView):
    model = Tournament
    context_object_name = "tournaments"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(location__icontains=q))
        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["tournaments/_tournament_rows.html"]
        return ["tournaments/tournament_list.html"]


class TournamentCreateView(CreateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def get_success_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.object.pk})


class TournamentUpdateView(UpdateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def get_success_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.object.pk})


def tournament_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Tournament, pk=pk).delete()
    return HttpResponse("")


class TournamentDetailView(DetailView):
    model = Tournament
    template_name = "tournaments/tournament_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competitions"] = self.object.competitions.all()
        return context


class CompetitionCreateView(CreateView):
    model = Competition
    form_class = CompetitionForm
    template_name = "tournaments/competition_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.tournament = get_object_or_404(Tournament, pk=kwargs["tournament_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tournament"] = self.tournament
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tournament"] = self.tournament
        return context

    def get_success_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.tournament.pk})


class CompetitionUpdateView(UpdateView):
    model = Competition
    form_class = CompetitionForm
    template_name = "tournaments/competition_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tournament"] = self.object.tournament
        return context

    def get_success_url(self):
        return reverse("tournaments:competition_detail", kwargs={"pk": self.object.pk})


def competition_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Competition, pk=pk).delete()
    return HttpResponse("")


class CompetitionDetailView(DetailView):
    model = Competition
    template_name = "tournaments/competition_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rule"] = getattr(self.object, "rule", None)
        context["stages"] = self.object.stages.all()
        context["participants"] = self.object.participants.select_related(
            "individual_player", "doubles_pair__player_one", "doubles_pair__player_two", "team"
        )
        context["participant_form"] = ParticipantForm(competition=self.object)
        return context


def competition_rule_edit(request, pk):
    competition = get_object_or_404(Competition, pk=pk)
    rule, _created = CompetitionRule.objects.get_or_create(competition=competition)
    if request.method == "POST":
        form = CompetitionRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            return redirect("tournaments:competition_detail", pk=competition.pk)
    else:
        form = CompetitionRuleForm(instance=rule)
    return render(request, "tournaments/competitionrule_form.html", {"form": form, "competition": competition})


class StageCreateView(CreateView):
    model = Stage
    form_class = StageForm
    template_name = "tournaments/stage_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.competition = get_object_or_404(Competition, pk=kwargs["competition_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["competition"] = self.competition
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competition"] = self.competition
        return context

    def get_success_url(self):
        return reverse("tournaments:competition_detail", kwargs={"pk": self.competition.pk})


class StageUpdateView(UpdateView):
    model = Stage
    form_class = StageForm
    template_name = "tournaments/stage_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competition"] = self.object.competition
        return context

    def get_success_url(self):
        return reverse("tournaments:stage_detail", kwargs={"pk": self.object.pk})


def stage_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Stage, pk=pk).delete()
    return HttpResponse("")


def stage_bracket_generate(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    seeded = request.POST.get("draw_mode") != "random"
    third_place = request.POST.get("third_place") == "on"
    try:
        generate_stage_bracket(stage, seeded=seeded, third_place=third_place)
    except (ScheduleAlreadyGeneratedError, NotEnoughParticipantsError) as exc:
        messages.error(request, str(exc))
    return redirect("tournaments:stage_detail", pk=stage.pk)


def stage_bracket_clear(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    stage = get_object_or_404(Stage, pk=pk)
    clear_stage_bracket(stage)
    return redirect("tournaments:stage_detail", pk=stage.pk)


def _round_label(round_number, total_rounds):
    from_final = total_rounds - round_number
    if from_final == 0:
        return _("Final")
    if from_final == 1:
        return _("Semifinal")
    if from_final == 2:
        return _("Quarterfinal")
    return _("Round %(n)s") % {"n": round_number}


class StageDetailView(DetailView):
    model = Stage
    template_name = "tournaments/stage_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = self.object.groups.all()
        if self.object.stage_format == StageFormat.KNOCKOUT:
            bracket_matches = list(
                self.object.matches.filter(group__isnull=True)
                .select_related("participant_a", "participant_b")
                .order_by("round_number", "bracket_slot")
            )
            non_third_place_rounds = [m.round_number for m in bracket_matches if not m.is_third_place]
            total_rounds = max(non_third_place_rounds, default=0)

            rounds = []
            third_place_matches = []
            for match in bracket_matches:
                if match.is_third_place:
                    third_place_matches.append(match)
                    continue
                if not rounds or rounds[-1]["round_number"] != match.round_number:
                    rounds.append(
                        {
                            "round_number": match.round_number,
                            "label": _round_label(match.round_number, total_rounds),
                            "matches": [],
                        }
                    )
                rounds[-1]["matches"].append(match)
            if third_place_matches:
                rounds.append({"round_number": total_rounds, "label": _("Third place"), "matches": third_place_matches})

            context["bracket_rounds"] = rounds
            context["has_bracket"] = bool(bracket_matches)
        return context


class GroupCreateView(CreateView):
    model = Group
    form_class = GroupForm
    template_name = "tournaments/group_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.stage = get_object_or_404(Stage, pk=kwargs["stage_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["stage"] = self.stage
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stage"] = self.stage
        return context

    def get_success_url(self):
        return reverse("tournaments:stage_detail", kwargs={"pk": self.stage.pk})


def group_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Group, pk=pk).delete()
    return HttpResponse("")


def _group_participant_panel_context(group):
    return {
        "group": group,
        "group_participants": group.group_participants.select_related(
            "participant__individual_player",
            "participant__doubles_pair__player_one",
            "participant__doubles_pair__player_two",
            "participant__team",
        ),
        "group_participant_form": GroupParticipantForm(group=group),
    }


class GroupDetailView(DetailView):
    model = Group
    template_name = "tournaments/group_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_group_participant_panel_context(self.object))
        context["schedule_matches"] = self.object.matches.select_related(
            "participant_a", "participant_b"
        ).order_by("round_number", "pk")
        context["standings"] = compute_group_standings(self.object)
        return context


def group_participant_add(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    group = get_object_or_404(Group, pk=pk)
    form = GroupParticipantForm(request.POST, group=group)
    if form.is_valid():
        form.save()
        context = _group_participant_panel_context(group)
    else:
        context = _group_participant_panel_context(group)
        context["group_participant_form"] = form
    return render(request, "tournaments/_group_participant_panel.html", context)


def group_participant_remove(request, pk, group_participant_id):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    group = get_object_or_404(Group, pk=pk)
    get_object_or_404(GroupParticipant, pk=group_participant_id, group=group).delete()
    return render(request, "tournaments/_group_participant_panel.html", _group_participant_panel_context(group))


def group_schedule_generate(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    group = get_object_or_404(Group, pk=pk)
    legs = 2 if request.POST.get("legs") == "2" else 1
    try:
        generate_group_schedule(group, legs=legs)
    except (ScheduleAlreadyGeneratedError, NotEnoughParticipantsError) as exc:
        messages.error(request, str(exc))
    return redirect("tournaments:group_detail", pk=group.pk)


def group_schedule_clear(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    group = get_object_or_404(Group, pk=pk)
    clear_group_schedule(group)
    return redirect("tournaments:group_detail", pk=group.pk)


def _participant_panel_context(competition):
    return {
        "competition": competition,
        "participants": competition.participants.select_related(
            "individual_player", "doubles_pair__player_one", "doubles_pair__player_two", "team"
        ),
        "participant_form": ParticipantForm(competition=competition),
    }


def participant_add(request, competition_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    form = ParticipantForm(request.POST, competition=competition)
    if form.is_valid():
        form.save()
        context = _participant_panel_context(competition)
    else:
        context = _participant_panel_context(competition)
        context["participant_form"] = form
    return render(request, "tournaments/_participant_panel.html", context)


def participant_delete(request, competition_pk, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    get_object_or_404(Participant, pk=pk, competition=competition).delete()
    return render(request, "tournaments/_participant_panel.html", _participant_panel_context(competition))
