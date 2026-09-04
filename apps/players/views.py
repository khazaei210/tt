from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

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


@staff_required
def player_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    return HttpResponse("")


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
