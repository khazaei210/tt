from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CompetitionForm, CompetitionRuleForm, GroupForm, ParticipantForm, StageForm, TournamentForm
from .models import Competition, CompetitionRule, Group, Participant, Stage, Tournament


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


class StageDetailView(DetailView):
    model = Stage
    template_name = "tournaments/stage_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = self.object.groups.all()
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
