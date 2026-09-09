import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.bale.services import notify_matches_created
from apps.core.csv_utils import csv_response
from apps.matches.services import (
    MatchAlreadyStartedError,
    NoKnockoutStageError,
    NotEnoughParticipantsError,
    ParticipantNotInBracketError,
    QualifiersNotConfiguredError,
    ScheduleAlreadyGeneratedError,
    StageNotCompleteError,
    advance_to_next_stage,
    clear_group_schedule,
    clear_stage_bracket,
    compute_group_standings,
    generate_group_schedule,
    generate_stage_bracket,
    swap_bracket_participants,
)
from apps.matches.team_tie import summarize_tie

from .forms import (
    BracketSwapForm,
    BulkParticipantForm,
    CompetitionForm,
    CompetitionRuleForm,
    GroupBulkCreateForm,
    GroupForm,
    GroupParticipantForm,
    GroupParticipantMoveForm,
    ParticipantForm,
    StageForm,
    TournamentForm,
)
from .models import (
    AuditAction,
    Competition,
    CompetitionRule,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    StaffRole,
    Tournament,
    TournamentAuditLog,
    TournamentStaff,
)
from .permissions import (
    MANAGEMENT_ROLES,
    TournamentManagerRequiredMixin,
    can_create_tournament,
    can_manage_tournament,
    tournament_manager_required,
)
from .services.dashboard import build_manager_dashboard
from .services.registration import (
    AlreadyRegisteredError,
    CannotWithdrawError,
    CompetitionFullError,
    NoPlayerProfileError,
    NotRegisteredError,
    RegistrationClosedError,
    UnsupportedParticipantTypeError,
    is_competition_full,
    register_self,
    unregister_self,
)
from .services.setup import (
    DuplicateGroupAssignmentError,
    InvalidGroupMoveError,
    NoGroupsAvailableError,
    NotRoundRobinStageError,
    StageLockedError,
    attach_elo_ratings,
    auto_assign_participants_to_groups,
    create_groups,
    ensure_stage_unlocked,
    lock_stage,
    move_participant_to_group,
    seed_participants_by_rating,
    suggested_group_count,
    unlock_stage,
)

logger = logging.getLogger(__name__)


_MATCH_NOTIFY_SELECT_RELATED = (
    "competition",
    "competition__tournament",
    "participant_a__individual_player",
    "participant_a__doubles_pair__player_one",
    "participant_a__doubles_pair__player_two",
    "participant_a__team",
    "participant_b__individual_player",
    "participant_b__doubles_pair__player_one",
    "participant_b__doubles_pair__player_two",
    "participant_b__team",
)


def _report_bale_notifications(request, matches_queryset):
    """Best-effort, after a draw/schedule is generated: tell every
    involved player their new match over Bale, and summarize the outcome
    for the staff member who triggered generation.

    notify_matches_created() already turns every expected Bale failure
    (unlinked player, API/transport error) into a status entry rather
    than an exception — the broad except below is only a last-resort net
    against a latent bug in that notification path, so it can never turn
    an already-successful draw/schedule generation into a 500 for staff.
    """
    try:
        results = notify_matches_created(matches_queryset.select_related(*_MATCH_NOTIFY_SELECT_RELATED))
    except Exception:
        logger.exception("Unexpected error while notifying players via Bale")
        return
    if not results:
        return
    sent = sum(1 for _player, status in results if status == "sent")
    unreachable = len(results) - sent
    if unreachable:
        messages.info(
            request,
            _(
                "Notified %(sent)s player(s) of their new match via Bale "
                "(%(unreachable)s not reachable — not linked yet, or delivery failed)."
            )
            % {"sent": sent, "unreachable": unreachable},
        )
    else:
        messages.info(request, _("Notified %(sent)s player(s) of their new match via Bale.") % {"sent": sent})


def _tournament_from_pk(request, pk, **kwargs):
    return get_object_or_404(Tournament, pk=pk)


def _tournament_from_competition_pk(request, pk, **kwargs):
    return get_object_or_404(Competition, pk=pk).tournament


def _tournament_from_competition_pk_kwarg(request, competition_pk, **kwargs):
    return get_object_or_404(Competition, pk=competition_pk).tournament


def _tournament_from_stage_pk(request, pk, **kwargs):
    return get_object_or_404(Stage, pk=pk).competition.tournament


def _tournament_from_group_pk(request, pk, **kwargs):
    return get_object_or_404(Group, pk=pk).stage.competition.tournament


@login_required
def manager_dashboard(request):
    """The Tournament Manager dashboard (CLAUDE.md section 25): tournaments
    the user manages (or every tournament, for a superuser), their
    progress, and their live/upcoming/completed matches. A user with no
    management role anywhere just sees an empty state, not a 403 — this
    is a personalized view, not a gated action.
    """
    return render(request, "tournaments/manager_dashboard.html", {"dashboard": build_manager_dashboard(request.user)})


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

    def get_context_data(self, **kwargs):
        """Per-row Edit/Delete controls must only render for tournaments
        this specific user can manage — management roles are granted per
        Tournament (TournamentStaff), not globally, so a manager of one
        tournament isn't automatically a manager of every other one listed
        here (CLAUDE.md section 26: never rely only on frontend
        visibility — the underlying views are already gated by
        TournamentManagerRequiredMixin/tournament_manager_required, this
        just keeps the buttons from being shown to someone who can't use
        them)."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        tournaments = context["tournaments"]
        if user.is_superuser:
            manageable_ids = {t.pk for t in tournaments}
        elif user.is_authenticated:
            manageable_ids = set(
                TournamentStaff.objects.filter(
                    user=user, role__in=MANAGEMENT_ROLES, tournament__in=tournaments
                ).values_list("tournament_id", flat=True)
            )
        else:
            manageable_ids = set()
        context["manageable_tournament_ids"] = manageable_ids
        context["can_create_tournament"] = can_create_tournament(user)
        return context


class TournamentCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def test_func(self):
        return can_create_tournament(self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        TournamentStaff.objects.create(tournament=self.object, user=self.request.user, role=StaffRole.TOURNAMENT_ADMIN)
        return response

    def get_success_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.object.pk})


class TournamentUpdateView(TournamentManagerRequiredMixin, UpdateView):
    model = Tournament
    form_class = TournamentForm
    template_name = "tournaments/tournament_form.html"

    def get_tournament(self):
        return get_object_or_404(Tournament, pk=self.kwargs["pk"])

    def get_success_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.object.pk})


@tournament_manager_required(_tournament_from_pk)
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
        can_manage = can_manage_tournament(self.request.user, self.object)
        context["can_manage"] = can_manage
        if can_manage:
            context["recent_activity"] = self.object.audit_log.select_related("actor")[:20]
        return context


class CompetitionCreateView(TournamentManagerRequiredMixin, CreateView):
    model = Competition
    form_class = CompetitionForm
    template_name = "tournaments/competition_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.tournament = get_object_or_404(Tournament, pk=kwargs["tournament_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_tournament(self):
        return self.tournament

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


class CompetitionUpdateView(TournamentManagerRequiredMixin, UpdateView):
    model = Competition
    form_class = CompetitionForm
    template_name = "tournaments/competition_form.html"

    def get_tournament(self):
        return get_object_or_404(Competition, pk=self.kwargs["pk"]).tournament

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tournament"] = self.object.tournament
        return context

    def get_success_url(self):
        return reverse("tournaments:competition_detail", kwargs={"pk": self.object.pk})


@tournament_manager_required(_tournament_from_competition_pk)
def competition_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Competition, pk=pk).delete()
    return HttpResponse("")


def _registration_panel_context(competition, user):
    entrant_count = competition.participants.entrants().count()
    my_participant = None
    player = getattr(user, "player_profile", None)
    if player is not None:
        my_participant = competition.participants.filter(individual_player=player).first()
    can_register = (
        user.is_authenticated
        and competition.registration_open
        and competition.participant_type == ParticipantType.INDIVIDUAL
        and player is not None
        and my_participant is None
        and not is_competition_full(competition)
    )
    can_unregister = (
        my_participant is not None
        and not my_participant.matches_as_participant_a.exists()
        and not my_participant.matches_as_participant_b.exists()
    )
    return {
        "competition": competition,
        "entrant_count": entrant_count,
        "my_participant": my_participant,
        "can_register": can_register,
        "can_unregister": can_unregister,
    }


class CompetitionDetailView(DetailView):
    model = Competition
    template_name = "tournaments/competition_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rule"] = getattr(self.object, "rule", None)
        context["stages"] = self.object.stages.all()
        context.update(_participant_panel_context(self.object))
        context.update(_registration_panel_context(self.object, self.request.user))
        context["can_manage"] = can_manage_tournament(self.request.user, self.object.tournament)
        context["can_award_ranking_points"] = self.object.ranking_category_id is not None
        return context


@tournament_manager_required(_tournament_from_competition_pk)
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


class StageCreateView(TournamentManagerRequiredMixin, CreateView):
    model = Stage
    form_class = StageForm
    template_name = "tournaments/stage_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.competition = get_object_or_404(Competition, pk=kwargs["competition_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_tournament(self):
        return self.competition.tournament

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


class StageUpdateView(TournamentManagerRequiredMixin, UpdateView):
    model = Stage
    form_class = StageForm
    template_name = "tournaments/stage_form.html"

    def get_tournament(self):
        return get_object_or_404(Stage, pk=self.kwargs["pk"]).competition.tournament

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["competition"] = self.object.competition
        return context

    def get_success_url(self):
        return reverse("tournaments:stage_detail", kwargs={"pk": self.object.pk})


@tournament_manager_required(_tournament_from_stage_pk)
def stage_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    get_object_or_404(Stage, pk=pk).delete()
    return HttpResponse("")


@tournament_manager_required(_tournament_from_stage_pk)
def stage_bracket_generate(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    seeded = request.POST.get("draw_mode") != "random"
    third_place = request.POST.get("third_place") == "on"
    try:
        generate_stage_bracket(stage, seeded=seeded, third_place=third_place)
    except (ScheduleAlreadyGeneratedError, NotEnoughParticipantsError, StageLockedError) as exc:
        messages.error(request, str(exc))
    else:
        _report_bale_notifications(request, stage.matches.ties())
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_advance(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    try:
        advance_to_next_stage(stage)
    except (
        NotEnoughParticipantsError,
        StageNotCompleteError,
        QualifiersNotConfiguredError,
        NoKnockoutStageError,
        ScheduleAlreadyGeneratedError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, _("Qualifiers advanced to the next stage."))
        next_stage = stage.competition.stages.filter(order=stage.order + 1, stage_format=StageFormat.KNOCKOUT).first()
        if next_stage is not None:
            _report_bale_notifications(request, next_stage.matches.ties())
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_auto_assign_groups(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    try:
        assigned = auto_assign_participants_to_groups(stage)
    except (NotRoundRobinStageError, NoGroupsAvailableError, StageLockedError) as exc:
        messages.error(request, str(exc))
    else:
        if assigned:
            messages.success(request, _("Assigned %(n)s participant(s) to groups.") % {"n": len(assigned)})
        else:
            messages.info(request, _("Every participant is already assigned to a group."))
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_generate_all_schedules(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    legs = 2 if request.POST.get("legs") == "2" else 1
    generated = []
    for group in stage.groups.order_by("order"):
        try:
            generate_group_schedule(group, legs=legs)
        except (ScheduleAlreadyGeneratedError, NotEnoughParticipantsError):
            continue
        generated.append(group)
    if generated:
        _report_bale_notifications(request, stage.matches.ties().filter(group__in=generated))
        messages.success(request, _("Generated schedules for %(n)s group(s).") % {"n": len(generated)})
    else:
        messages.info(request, _("No groups were eligible for schedule generation (already scheduled, or not enough participants)."))
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_bracket_clear(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    stage = get_object_or_404(Stage, pk=pk)
    try:
        clear_stage_bracket(stage)
    except StageLockedError as exc:
        messages.error(request, str(exc))
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_bracket_swap(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    form = BracketSwapForm(request.POST, stage=stage)
    if form.is_valid():
        try:
            swap_bracket_participants(
                stage,
                form.cleaned_data["participant_a"].pk,
                form.cleaned_data["participant_b"].pk,
                performed_by=request.user,
            )
        except (ParticipantNotInBracketError, MatchAlreadyStartedError, StageLockedError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Swapped the two participants' bracket positions."))
    else:
        for error in form.non_field_errors():
            messages.error(request, error)
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_lock(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    lock_stage(stage, performed_by=request.user)
    messages.success(request, _("Stage locked. Its groups and bracket can no longer be changed until unlocked."))
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_unlock(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    unlock_stage(stage, performed_by=request.user)
    messages.success(request, _("Stage unlocked."))
    return redirect("tournaments:stage_detail", pk=stage.pk)


@tournament_manager_required(_tournament_from_stage_pk)
def stage_groups_bulk_create(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    stage = get_object_or_404(Stage, pk=pk)
    form = GroupBulkCreateForm(request.POST)
    if form.is_valid():
        try:
            created = create_groups(stage, form.cleaned_data["count"], performed_by=request.user)
        except (NotRoundRobinStageError, StageLockedError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Created %(n)s group(s).") % {"n": len(created)})
    else:
        for error in form.errors.get("count", []):
            messages.error(request, error)
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
        if self.object.stage_format == StageFormat.ROUND_ROBIN:
            next_stage = self.object.competition.stages.filter(
                order=self.object.order + 1, stage_format=StageFormat.KNOCKOUT
            ).first()
            context["next_knockout_stage"] = next_stage
            context["can_advance_qualifiers"] = (
                bool(self.object.qualifiers_per_group)
                and next_stage is not None
                and not next_stage.matches.ties().exists()
            )
            participant_count = self.object.competition.participants.entrants().count()
            context["group_bulk_create_form"] = GroupBulkCreateForm(
                initial={"count": suggested_group_count(participant_count)}
            )
        is_team = self.object.competition.participant_type == ParticipantType.TEAM
        context["is_team_competition"] = is_team
        if self.object.stage_format == StageFormat.KNOCKOUT:
            bracket_matches = list(
                self.object.matches.ties().filter(group__isnull=True)
                .select_related("participant_a", "participant_b")
                .order_by("round_number", "bracket_slot")
            )
            if is_team:
                for match in bracket_matches:
                    match.tie_summary = summarize_tie(match)
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
            if bracket_matches:
                context["bracket_swap_form"] = BracketSwapForm(stage=self.object)
        context["can_manage"] = can_manage_tournament(self.request.user, self.object.competition.tournament)
        return context


class GroupCreateView(TournamentManagerRequiredMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = "tournaments/group_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.stage = get_object_or_404(Stage, pk=kwargs["stage_pk"])
        if self.stage.is_locked and request.method == "POST":
            messages.error(request, _("This stage's draw is locked. An administrator must unlock it before making changes."))
            return redirect("tournaments:stage_detail", pk=self.stage.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_tournament(self):
        return self.stage.competition.tournament

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


@tournament_manager_required(_tournament_from_group_pk)
def group_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    group = get_object_or_404(Group, pk=pk)
    if group.stage.is_locked:
        return HttpResponse(status=409)
    group.delete()
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
        "other_groups": Group.objects.filter(stage_id=group.stage_id).exclude(pk=group.pk),
        "stage_locked": group.stage.is_locked,
        # The two HTMX views below re-render this partial standalone and are
        # already gated by @tournament_manager_required, so reaching them
        # implies can_manage. GroupDetailView overrides this with the real
        # per-viewer value after calling this helper.
        "can_manage": True,
    }


class GroupDetailView(DetailView):
    model = Group
    template_name = "tournaments/group_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_group_participant_panel_context(self.object))
        is_team = self.object.stage.competition.participant_type == ParticipantType.TEAM
        context["schedule_matches"] = self.object.matches.ties().select_related(
            "participant_a", "participant_b"
        ).order_by("round_number", "pk")
        if is_team:
            for match in context["schedule_matches"]:
                match.tie_summary = summarize_tie(match)
        context["is_team_competition"] = is_team
        context["standings"] = compute_group_standings(self.object)
        context["can_manage"] = can_manage_tournament(self.request.user, self.object.stage.competition.tournament)
        return context


def group_standings_csv(request, pk):
    group = get_object_or_404(Group, pk=pk)
    is_team = group.stage.competition.participant_type == ParticipantType.TEAM
    header = [_("Rank"), _("Participant"), _("Played"), _("Won"), _("Lost"), _("Match points")]
    if is_team:
        header += [_("Individual matches won"), _("Individual matches lost")]
    header += [_("Sets won"), _("Sets lost"), _("Set difference"), _("Points scored"), _("Points conceded"), _("Point difference")]

    rows = []
    for row in compute_group_standings(group):
        values = [row["rank"], row["participant"].display_name, row["played"], row["wins"], row["losses"], row["match_points"]]
        if is_team:
            values += [row["individual_matches_won"], row["individual_matches_lost"]]
        values += [
            row["sets_won"], row["sets_lost"], row["set_difference"], row["points_scored"], row["points_conceded"],
            row["point_difference"],
        ]
        rows.append(values)
    return csv_response(f"standings-{group.pk}.csv", header, rows)


@tournament_manager_required(_tournament_from_group_pk)
def group_participant_add(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    group = get_object_or_404(Group, pk=pk)
    try:
        ensure_stage_unlocked(group.stage)
    except StageLockedError as exc:
        context = _group_participant_panel_context(group)
        context["action_error"] = str(exc)
        return render(request, "tournaments/_group_participant_panel.html", context)
    form = GroupParticipantForm(request.POST, group=group)
    if form.is_valid():
        form.save()
        context = _group_participant_panel_context(group)
    else:
        context = _group_participant_panel_context(group)
        context["group_participant_form"] = form
    return render(request, "tournaments/_group_participant_panel.html", context)


@tournament_manager_required(_tournament_from_group_pk)
def group_participant_remove(request, pk, group_participant_id):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    group = get_object_or_404(Group, pk=pk)
    try:
        ensure_stage_unlocked(group.stage)
    except StageLockedError as exc:
        context = _group_participant_panel_context(group)
        context["action_error"] = str(exc)
        return render(request, "tournaments/_group_participant_panel.html", context)
    get_object_or_404(GroupParticipant, pk=group_participant_id, group=group).delete()
    return render(request, "tournaments/_group_participant_panel.html", _group_participant_panel_context(group))


@tournament_manager_required(_tournament_from_group_pk)
def group_participant_move(request, pk, group_participant_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    group = get_object_or_404(Group, pk=pk)
    group_participant = get_object_or_404(GroupParticipant, pk=group_participant_id, group=group)
    form = GroupParticipantMoveForm(request.POST, group_participant=group_participant)
    context = _group_participant_panel_context(group)
    if form.is_valid():
        try:
            move_participant_to_group(group_participant, form.cleaned_data["target_group"], performed_by=request.user)
        except (InvalidGroupMoveError, DuplicateGroupAssignmentError, StageLockedError) as exc:
            context["action_error"] = str(exc)
        else:
            context = _group_participant_panel_context(group)
    else:
        context["action_error"] = "; ".join(e for errs in form.errors.values() for e in errs)
    return render(request, "tournaments/_group_participant_panel.html", context)


@tournament_manager_required(_tournament_from_group_pk)
def group_schedule_generate(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    group = get_object_or_404(Group, pk=pk)
    legs = 2 if request.POST.get("legs") == "2" else 1
    try:
        generate_group_schedule(group, legs=legs)
    except (ScheduleAlreadyGeneratedError, NotEnoughParticipantsError) as exc:
        messages.error(request, str(exc))
    else:
        _report_bale_notifications(request, group.matches.ties())
    return redirect("tournaments:group_detail", pk=group.pk)


@tournament_manager_required(_tournament_from_group_pk)
def group_schedule_clear(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    group = get_object_or_404(Group, pk=pk)
    clear_group_schedule(group)
    return redirect("tournaments:group_detail", pk=group.pk)


def _participant_panel_context(competition):
    # is_tie_slot=False: this panel manages the competition's own draw
    # entrants; a Team competition's on-demand tie-slot participants
    # (one per nominated player, see Participant.is_tie_slot) aren't
    # entrants of this competition and would otherwise clutter this list.
    participants = list(
        competition.participants.filter(is_tie_slot=False).select_related(
            "individual_player", "doubles_pair__player_one", "doubles_pair__player_two", "team"
        )
    )
    attach_elo_ratings(participants, competition.ranking_category)
    return {
        "competition": competition,
        "participants": participants,
        "participant_form": ParticipantForm(competition=competition),
        "bulk_participant_form": BulkParticipantForm(competition=competition),
        # Same reasoning as _group_participant_panel_context above: the
        # HTMX views that render this standalone are already gated by
        # @tournament_manager_required. CompetitionDetailView overrides
        # this with the real per-viewer value.
        "can_manage": True,
    }


@tournament_manager_required(_tournament_from_competition_pk_kwarg)
def participant_add(request, competition_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    form = ParticipantForm(request.POST, competition=competition)
    if form.is_valid():
        participant = form.save()
        TournamentAuditLog.objects.log(
            competition.tournament,
            request.user,
            AuditAction.PARTICIPANT_ADDED_BY_STAFF,
            _("%(participant)s added to %(competition)s by staff.")
            % {"participant": participant.display_name, "competition": competition.name},
        )
        context = _participant_panel_context(competition)
    else:
        context = _participant_panel_context(competition)
        context["participant_form"] = form
    return render(request, "tournaments/_participant_panel.html", context)


@tournament_manager_required(_tournament_from_competition_pk_kwarg)
def participant_bulk_add(request, competition_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    form = BulkParticipantForm(request.POST, competition=competition)
    if form.is_valid():
        participants = form.save()
        TournamentAuditLog.objects.log(
            competition.tournament,
            request.user,
            AuditAction.PARTICIPANT_ADDED_BY_STAFF,
            _("%(n)s participant(s) added to %(competition)s by staff.")
            % {"n": len(participants), "competition": competition.name},
        )
        context = _participant_panel_context(competition)
    else:
        context = _participant_panel_context(competition)
        context["bulk_participant_form"] = form
    return render(request, "tournaments/_participant_panel.html", context)


@tournament_manager_required(_tournament_from_competition_pk_kwarg)
def competition_seed_by_rating(request, competition_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    seed_participants_by_rating(competition)
    return render(request, "tournaments/_participant_panel.html", _participant_panel_context(competition))


@tournament_manager_required(_tournament_from_competition_pk_kwarg)
def participant_delete(request, competition_pk, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    competition = get_object_or_404(Competition, pk=competition_pk)
    participant = get_object_or_404(Participant, pk=pk, competition=competition)
    display_name = participant.display_name
    participant.delete()
    TournamentAuditLog.objects.log(
        competition.tournament,
        request.user,
        AuditAction.PARTICIPANT_REMOVED_BY_STAFF,
        _("%(participant)s removed from %(competition)s by staff.")
        % {"participant": display_name, "competition": competition.name},
    )
    return render(request, "tournaments/_participant_panel.html", _participant_panel_context(competition))


@login_required
def competition_register(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=pk)
    try:
        register_self(competition, request.user)
    except (
        RegistrationClosedError,
        CompetitionFullError,
        UnsupportedParticipantTypeError,
        NoPlayerProfileError,
        AlreadyRegisteredError,
    ) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, _("You're registered for %(competition)s.") % {"competition": competition.name})
    return redirect("tournaments:competition_detail", pk=competition.pk)


@login_required
def competition_unregister(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    competition = get_object_or_404(Competition, pk=pk)
    try:
        unregister_self(competition, request.user)
    except (NotRegisteredError, CannotWithdrawError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, _("Your registration has been withdrawn."))
    return redirect("tournaments:competition_detail", pk=competition.pk)
