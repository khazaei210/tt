from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import CreateView, ListView, UpdateView

from apps.accounts.services import (
    PlayerAlreadyHasLoginError,
    PlayerHasNoLoginError,
    create_player_login,
    reset_player_login_password,
    suggest_username,
)
from apps.core.permissions import StaffRequiredMixin, is_staff_user, staff_required

from .forms import DoublesPairForm, PlayerForm
from .models import DoublesPair, Player


class PlayerListView(ListView):
    model = Player
    context_object_name = "players"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(club__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_manage"] = is_staff_user(self.request.user)
        return context

    def get_template_names(self):
        if self.request.htmx:
            return ["players/_player_rows.html"]
        return ["players/player_list.html"]


class PlayerCreateView(StaffRequiredMixin, CreateView):
    model = Player
    form_class = PlayerForm
    template_name = "players/player_form.html"
    success_url = reverse_lazy("players:list")


class PlayerUpdateView(StaffRequiredMixin, UpdateView):
    model = Player
    form_class = PlayerForm
    template_name = "players/player_form.html"
    success_url = reverse_lazy("players:list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object.user_id is None:
            context["suggested_username"] = suggest_username(self.object)
        return context


@staff_required
def player_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    return HttpResponse("")


@staff_required
def player_create_login(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    player = get_object_or_404(Player, pk=pk)
    username = request.POST.get("username", "").strip() or None
    try:
        user, raw_password = create_player_login(player, username=username)
    except PlayerAlreadyHasLoginError:
        messages.error(request, _("This player already has a login."))
    else:
        messages.success(
            request,
            _(
                "Login created for %(player)s — username: %(username)s, password: %(password)s "
                "(shown once now, save it before leaving this page)."
            )
            % {"player": player.full_name, "username": user.username, "password": raw_password},
        )
    return redirect("players:edit", pk=player.pk)


@staff_required
def player_reset_password(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    player = get_object_or_404(Player, pk=pk)
    try:
        raw_password = reset_player_login_password(player)
    except PlayerHasNoLoginError:
        messages.error(request, _("This player doesn't have a login yet."))
    else:
        messages.success(
            request,
            _(
                "New password for %(player)s (username: %(username)s): %(password)s "
                "(shown once now, save it before leaving this page)."
            )
            % {"player": player.full_name, "username": player.user.username, "password": raw_password},
        )
    return redirect("players:edit", pk=player.pk)


class DoublesPairListView(ListView):
    model = DoublesPair
    context_object_name = "pairs"
    template_name = "players/doubles_pair_list.html"

    def get_queryset(self):
        return super().get_queryset().select_related("player_one", "player_two")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_manage"] = is_staff_user(self.request.user)
        return context


class DoublesPairCreateView(StaffRequiredMixin, CreateView):
    model = DoublesPair
    form_class = DoublesPairForm
    template_name = "players/doubles_pair_form.html"
    success_url = reverse_lazy("players:pair_list")


@staff_required
def doubles_pair_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    pair = get_object_or_404(DoublesPair, pk=pk)
    pair.delete()
    return HttpResponse("")
