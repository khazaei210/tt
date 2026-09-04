from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.players.models import Player


class Team(models.Model):
    name = models.CharField(_("Name"), max_length=150, unique=True)
    short_name = models.CharField(_("Short name"), max_length=20, blank=True)
    country = models.CharField(_("Country"), max_length=100, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    members = models.ManyToManyField(Player, through="TeamMembership", related_name="teams")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("teams:detail", kwargs={"pk": self.pk})


class TeamMembership(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="team_memberships")
    joined_on = models.DateField(_("Joined on"), null=True, blank=True)
    is_active = models.BooleanField(_("Active on roster"), default=True)

    class Meta:
        ordering = ["player__last_name", "player__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["team", "player"], name="unique_team_player"),
        ]

    def __str__(self):
        return f"{self.player} @ {self.team}"
