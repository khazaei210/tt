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
    # RESTRICT, not PROTECT, on the three Participant FKs below: deleting a
    # single Participant while it still has matches must still be blocked,
    # but deleting an entire Tournament has to cascade through Stage/Match
    # down to Participant in one operation — PROTECT would refuse that even
    # though the referencing Match rows are being deleted in the same
    # cascade, since PROTECT is unconditional. RESTRICT allows exactly that
    # case while still blocking a standalone Participant delete.
    participant_a = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="matches_as_participant_a",
    )
    participant_b = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="matches_as_participant_b",
    )
    is_bye = models.BooleanField(_("BYE"), default=False)
    is_third_place = models.BooleanField(_("Third place match"), default=False)
    status = models.CharField(_("Status"), max_length=20, choices=MatchStatus.choices, default=MatchStatus.SCHEDULED)
    winner = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
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


class MatchCorrectionAction(models.TextChoices):
    SET_SCORE_CHANGED = "set_score_changed", _("Set score changed")
    SET_SCORE_DELETED = "set_score_deleted", _("Set score deleted")
    RESULT_CORRECTED = "result_corrected", _("Result corrected")


class MatchCorrection(models.Model):
    """An audit trail entry for a change to a value that was already
    recorded — as opposed to normal progress (entering the next set,
    reaching a first-time result).

    CLAUDE.md section 33: completed results aren't silently overwritten,
    and corrections should stay traceable. previous_value/new_value are
    short human-readable summaries (e.g. "11-8" or "Walkover — winner:
    Ali Rezaei") rather than a generic structured diff — enough to show
    what changed on the match page without a bespoke schema per action
    type.
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="corrections")
    action = models.CharField(_("Action"), max_length=30, choices=MatchCorrectionAction.choices)
    set_number = models.PositiveSmallIntegerField(_("Set number"), null=True, blank=True)
    previous_value = models.CharField(_("Previous value"), max_length=200)
    new_value = models.CharField(_("New value"), max_length=200, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="match_corrections",
        verbose_name=_("Performed by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Match correction")

    def __str__(self):
        return f"{self.match} — {self.get_action_display()}: {self.previous_value} → {self.new_value}"
