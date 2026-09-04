from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import PlayerForm
from .models import Player


class PlayerListView(ListView):
    model = Player
    context_object_name = "players"

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(club__icontains=q))
        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["players/_player_rows.html"]
        return ["players/player_list.html"]


class PlayerCreateView(CreateView):
    model = Player
    form_class = PlayerForm
    template_name = "players/player_form.html"
    success_url = reverse_lazy("players:list")


class PlayerUpdateView(UpdateView):
    model = Player
    form_class = PlayerForm
    template_name = "players/player_form.html"
    success_url = reverse_lazy("players:list")


def player_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    return HttpResponse("")
