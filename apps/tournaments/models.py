from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class TournamentStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    UPCOMING = "upcoming", _("Upcoming")
    ONGOING = "ongoing", _("Ongoing")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")


class Tournament(models.Model):
    name = models.CharField(_("Name"), max_length=200)
    location = models.CharField(_("Location"), max_length=200, blank=True)
    start_date = models.DateField(_("Start date"), null=True, blank=True)
    end_date = models.DateField(_("End date"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=20, choices=TournamentStatus.choices, default=TournamentStatus.DRAFT)
    description = models.TextField(_("Description"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tournaments:detail", kwargs={"pk": self.pk})


class StaffRole(models.TextChoices):
    TOURNAMENT_ADMIN = "tournament_admin", _("Tournament Admin")
    TOURNAMENT_MANAGER = "tournament_manager", _("Tournament Manager")
    REFEREE = "referee", _("Referee")
    SCOREKEEPER = "scorekeeper", _("Scorekeeper")


class TournamentStaff(models.Model):
    """A user's role on a specific Tournament.

    Deliberately per-tournament rather than a global Django Group/
    Permission: the same person can be a Tournament Admin for one
    tournament and have no role at all on another. Super Admin (Django's
    is_superuser) and Viewer (anyone, including anonymous — all read views
    are public) don't need a row here.
    """

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="staff")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tournament_roles")
    role = models.CharField(_("Role"), max_length=30, choices=StaffRole.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tournament", "role", "user"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "user", "role"], name="unique_staff_role_per_tournament"),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_role_display()} ({self.tournament})"


class ParticipantType(models.TextChoices):
    INDIVIDUAL = "individual", _("Individual")
    DOUBLES = "doubles", _("Doubles")
    TEAM = "team", _("Team")


class Competition(models.Model):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="competitions")
    name = models.CharField(_("Name"), max_length=200)
    participant_type = models.CharField(_("Participant type"), max_length=20, choices=ParticipantType.choices)
    is_active = models.BooleanField(_("Active"), default=True)
    ranking_category = models.ForeignKey(
        "rankings.RankingCategory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="competitions",
        verbose_name=_("Ranking category"),
        help_text=_(
            "Elo ratings update after every match, and final placements can award points, to this global "
            "ranking. Defaults to the shared 'Overall' category automatically — clear this to keep a "
            "specific competition (e.g. a casual friendly) out of the global ranking."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tournament", "name"]
        constraints = [
            models.UniqueConstraint(fields=["tournament", "name"], name="unique_competition_name_per_tournament"),
        ]

    def __str__(self):
        return f"{self.name} ({self.tournament.name})"

    def get_absolute_url(self):
        return reverse("tournaments:competition_detail", kwargs={"pk": self.pk})

    def save(self, *args, **kwargs):
        if self._state.adding and self.ranking_category_id is None:
            from apps.rankings.services import get_default_ranking_category

            self.ranking_category = get_default_ranking_category()
        super().save(*args, **kwargs)


class CompetitionRule(models.Model):
    BEST_OF_CHOICES = [(3, _("Best of 3")), (5, _("Best of 5")), (7, _("Best of 7"))]

    competition = models.OneToOneField(Competition, on_delete=models.CASCADE, related_name="rule")
    best_of_sets = models.PositiveSmallIntegerField(_("Best of sets"), choices=BEST_OF_CHOICES, default=5)
    points_per_set = models.PositiveSmallIntegerField(_("Points per set"), default=11)
    win_by = models.PositiveSmallIntegerField(_("Win by"), default=2)
    deciding_set_points = models.PositiveSmallIntegerField(
        _("Deciding set points"),
        null=True,
        blank=True,
        help_text=_("Leave blank to use the same points as other sets."),
    )
    cap_at = models.PositiveSmallIntegerField(
        _("Hard cap"),
        null=True,
        blank=True,
        help_text=_("Optional hard cap on a set's winning score, regardless of win-by-N."),
    )

    def __str__(self):
        return f"{_('Rules for')} {self.competition}"


class StageFormat(models.TextChoices):
    ROUND_ROBIN = "round_robin", _("Round robin")
    KNOCKOUT = "knockout", _("Knockout")


class Stage(models.Model):
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(_("Name"), max_length=150)
    stage_format = models.CharField(_("Format"), max_length=20, choices=StageFormat.choices)
    order = models.PositiveIntegerField(_("Order"), default=0)
    qualifiers_per_group = models.PositiveIntegerField(
        _("Qualifiers per group"),
        null=True,
        blank=True,
        help_text=_(
            "For a round-robin stage only: how many top finishers from each group advance to the "
            "competition's next (knockout) stage."
        ),
    )

    class Meta:
        ordering = ["competition", "order"]
        constraints = [
            models.UniqueConstraint(fields=["competition", "order"], name="unique_stage_order_per_competition"),
        ]

    def __str__(self):
        return f"{self.name} — {self.competition}"


class Group(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="groups")
    name = models.CharField(_("Name"), max_length=100)
    order = models.PositiveIntegerField(_("Order"), default=0)

    class Meta:
        ordering = ["stage", "order"]
        constraints = [
            models.UniqueConstraint(fields=["stage", "name"], name="unique_group_name_per_stage"),
        ]

    def __str__(self):
        return f"{self.name} — {self.stage}"


class Participant(models.Model):
    """A generic entrant in a Competition: an individual player, a doubles
    pair, or a team, depending on the competition's participant_type — plus
    a BYE placeholder used by draw generation (added in a later phase).
    """

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="participants")
    participant_type = models.CharField(_("Type"), max_length=20, choices=ParticipantType.choices)
    individual_player = models.ForeignKey(
        "players.Player", null=True, blank=True, on_delete=models.PROTECT, related_name="tournament_participations"
    )
    doubles_pair = models.ForeignKey(
        "players.DoublesPair", null=True, blank=True, on_delete=models.PROTECT, related_name="tournament_participations"
    )
    team = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="tournament_participations"
    )
    display_name = models.CharField(_("Display name"), max_length=200, blank=True)
    seed = models.PositiveIntegerField(_("Seed"), null=True, blank=True)
    is_bye = models.BooleanField(_("BYE"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["competition", "seed", "display_name"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        is_bye=True,
                        individual_player__isnull=True,
                        doubles_pair__isnull=True,
                        team__isnull=True,
                    )
                    | models.Q(
                        is_bye=False,
                        participant_type=ParticipantType.INDIVIDUAL,
                        individual_player__isnull=False,
                        doubles_pair__isnull=True,
                        team__isnull=True,
                    )
                    | models.Q(
                        is_bye=False,
                        participant_type=ParticipantType.DOUBLES,
                        individual_player__isnull=True,
                        doubles_pair__isnull=False,
                        team__isnull=True,
                    )
                    | models.Q(
                        is_bye=False,
                        participant_type=ParticipantType.TEAM,
                        individual_player__isnull=True,
                        doubles_pair__isnull=True,
                        team__isnull=False,
                    )
                ),
                name="participant_reference_matches_type",
            ),
            models.UniqueConstraint(
                fields=["competition", "seed"],
                condition=models.Q(seed__isnull=False),
                name="unique_seed_per_competition",
            ),
        ]

    def __str__(self):
        return self.display_name or str(_("BYE"))

    def save(self, *args, **kwargs):
        if self.is_bye:
            self.display_name = self.display_name or str(_("BYE"))
        elif not self.display_name:
            if self.participant_type == ParticipantType.INDIVIDUAL and self.individual_player_id:
                self.display_name = self.individual_player.full_name
            elif self.participant_type == ParticipantType.DOUBLES and self.doubles_pair_id:
                self.display_name = str(self.doubles_pair)
            elif self.participant_type == ParticipantType.TEAM and self.team_id:
                self.display_name = self.team.name
        super().save(*args, **kwargs)


class GroupParticipant(models.Model):
    """Placement of a competition Participant into one Group of a Stage.

    Kept as its own table (rather than a FK on Participant) because a
    Participant is scoped to a Competition, not to a single Stage — a
    competition can have a group stage followed by a knockout stage, and
    each needs its own, independent grouping of the same participants.
    """

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="group_participants")
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="group_assignments")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "participant"], name="unique_participant_per_group"),
        ]

    def __str__(self):
        return f"{self.participant} in {self.group}"
