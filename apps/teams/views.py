from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.permissions import StaffRequiredMixin, is_staff_user, staff_required

from .forms import TeamForm, TeamMembershipForm
from .models import Team, TeamMembership


class TeamListView(ListView):
    model = Team
    context_object_name = "teams"

    def get_queryset(self):
        qs = super().get_queryset().annotate(member_count=Count("memberships"))
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(short_name__icontains=q) | Q(country__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_manage"] = is_staff_user(self.request.user)
        return context

    def get_template_names(self):
        if self.request.htmx:
            return ["teams/_team_rows.html"]
        return ["teams/team_list.html"]


class TeamCreateView(StaffRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = "teams/team_form.html"
    success_url = reverse_lazy("teams:list")


class TeamUpdateView(StaffRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = "teams/team_form.html"
    success_url = reverse_lazy("teams:list")


class TeamDetailView(DetailView):
    model = Team
    template_name = "teams/team_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["memberships"] = self.object.memberships.select_related("player")
        context["membership_form"] = TeamMembershipForm(team=self.object)
        context["can_manage"] = is_staff_user(self.request.user)
        return context


@staff_required
def team_delete(request, pk):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    team = get_object_or_404(Team, pk=pk)
    team.delete()
    return HttpResponse("")


@staff_required
def team_member_add(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    team = get_object_or_404(Team, pk=pk)
    form = TeamMembershipForm(request.POST, team=team)
    if form.is_valid():
        form.save()
        form = TeamMembershipForm(team=team)
    return render(
        request,
        "teams/_roster_panel.html",
        {
            "team": team,
            "memberships": team.memberships.select_related("player"),
            "membership_form": form,
            # Guaranteed by @staff_required above.
            "can_manage": True,
        },
    )


@staff_required
def team_member_remove(request, pk, membership_id):
    if request.method not in ("DELETE", "POST"):
        return HttpResponseNotAllowed(["DELETE", "POST"])
    team = get_object_or_404(Team, pk=pk)
    get_object_or_404(TeamMembership, pk=membership_id, team=team).delete()
    return render(
        request,
        "teams/_roster_panel.html",
        {
            "team": team,
            "memberships": team.memberships.select_related("player"),
            "membership_form": TeamMembershipForm(team=team),
            "can_manage": True,
        },
    )
