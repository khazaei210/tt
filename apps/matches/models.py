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


class Match(models.Model):
    """A single match between two Participants.

    This is deliberately minimal for now: no MatchSet/scoring yet (that
    needs CompetitionRule-aware score validation, added in a later phase).
    For this phase a Match only records the schedule — who plays whom, in
    which round of which group — produced by a scheduling engine such as
    the round-robin service.
    """

    competition = models.ForeignKey("tournaments.Competition", on_delete=models.CASCADE, related_name="matches")
    stage = models.ForeignKey("tournaments.Stage", on_delete=models.CASCADE, related_name="matches")
    group = models.ForeignKey(
        "tournaments.Group", null=True, blank=True, on_delete=models.CASCADE, related_name="matches"
    )
    round_number = models.PositiveIntegerField(_("Round"))
    participant_a = models.ForeignKey(
        "tournaments.Participant", on_delete=models.PROTECT, related_name="matches_as_participant_a"
    )
    participant_b = models.ForeignKey(
        "tournaments.Participant", on_delete=models.PROTECT, related_name="matches_as_participant_b"
    )
    status = models.CharField(_("Status"), max_length=20, choices=MatchStatus.choices, default=MatchStatus.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["group", "round_number", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(participant_a=models.F("participant_b")),
                name="match_participants_distinct",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "round_number"]),
        ]

    def __str__(self):
        return f"{self.participant_a} vs {self.participant_b} ({_('Round')} {self.round_number})"
