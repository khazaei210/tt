from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MatchStatus(models.TextChoices):
    SCHEDULED = "scheduled", _("Scheduled")
    READY = "ready", _("Ready")
    LIVE = "live", _("Live")
    COMPLETED = "completed", _("Completed")
    CANCELLED = "cancelled", _("Cancelled")
    POSTPONED = "postponed", _("Postponed")
    WALKOVER = "walkover", _("Walkover")
    RETIRED = "retired", _("Retired")
    DEFAULT = "default", _("Default")


# A match in one of these statuses has a decided winner and is done being
# played — further changes are "corrections", not normal progress (see
# services.py's allow_correction guard on every function that can reach one
# of these statuses; CLAUDE.md section 33: completed results aren't
# silently overwritten).
TERMINAL_MATCH_STATUSES = (MatchStatus.COMPLETED, MatchStatus.WALKOVER, MatchStatus.RETIRED, MatchStatus.DEFAULT)


class Match(models.Model):
    """A single match between two Participants.

    participant_a/b are nullable because a knockout match beyond Round 1
    can genuinely have an undetermined opponent (pending an earlier
    match's result) — that's different from a BYE, which is a real
    Participant row (Participant.is_bye=True) substituted at bracket
    generation time, keeping "this match's two participants" a uniform
    concept everywhere except truly-not-yet-known future rounds.
    """

    competition = models.ForeignKey("tournaments.Competition", on_delete=models.CASCADE, related_name="matches")
    stage = models.ForeignKey("tournaments.Stage", on_delete=models.CASCADE, related_name="matches")
    group = models.ForeignKey(
        "tournaments.Group", null=True, blank=True, on_delete=models.CASCADE, related_name="matches"
    )
    round_number = models.PositiveIntegerField(_("Round"))
    bracket_slot = models.IntegerField(
        _("Bracket slot"),
        null=True,
        blank=True,
        help_text=_("Position within the round, for knockout bracket rendering/progression. Unused for round robin."),
    )
    participant_a = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matches_as_participant_a",
    )
    participant_b = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matches_as_participant_b",
    )
    is_bye = models.BooleanField(_("BYE"), default=False)
    is_third_place = models.BooleanField(_("Third place match"), default=False)
    status = models.CharField(_("Status"), max_length=20, choices=MatchStatus.choices, default=MatchStatus.SCHEDULED)
    winner = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matches_won",
    )
    referee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matches_refereed",
        verbose_name=_("Referee"),
    )
    scorekeeper = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matches_scorekept",
        verbose_name=_("Scorekeeper"),
    )
    start_time = models.DateTimeField(_("Start time"), null=True, blank=True)
    end_time = models.DateTimeField(_("End time"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group", "round_number", "bracket_slot", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(participant_a=models.F("participant_b")),
                name="match_participants_distinct",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(winner__isnull=True)
                    | models.Q(winner=models.F("participant_a"))
                    | models.Q(winner=models.F("participant_b"))
                ),
                name="match_winner_is_a_participant",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "round_number"]),
            models.Index(fields=["stage", "round_number"]),
        ]

    def __str__(self):
        a = self.participant_a or _("TBD")
        b = self.participant_b or _("TBD")
        return f"{a} vs {b} ({_('Round')} {self.round_number})"


class MatchSet(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="sets")
    set_number = models.PositiveSmallIntegerField(_("Set number"))
    participant_a_score = models.PositiveSmallIntegerField(_("Score A"))
    participant_b_score = models.PositiveSmallIntegerField(_("Score B"))

    class Meta:
        ordering = ["match", "set_number"]
        constraints = [
            models.UniqueConstraint(fields=["match", "set_number"], name="unique_set_number_per_match"),
        ]

    def __str__(self):
        return f"{_('Set')} {self.set_number}: {self.participant_a_score}-{self.participant_b_score}"
