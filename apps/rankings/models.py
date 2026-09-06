from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class RankingCategory(models.Model):
    """A global ranking board, e.g. "Men's Singles" or "Women's Doubles".

    Deliberately independent of Competition — the same category accumulates
    points across every tournament's matching competition, which is the
    whole point of a ranking as distinct from a single tournament's
    standings (see CLAUDE.md section 19).
    """

    name = models.CharField(_("Name"), max_length=150, unique=True)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Ranking category")
        verbose_name_plural = _("Ranking categories")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("rankings:category_detail", kwargs={"pk": self.pk})


class RankingPointsScale(models.Model):
    """How many ranking points a given final placement earns in a category.

    placement 1 = champion, 2 = runner-up, and so on. Kept as data rather
    than a hard-coded formula so each category can define its own scale
    (CLAUDE.md section 16/37: don't hard-code business rules).
    """

    category = models.ForeignKey(RankingCategory, on_delete=models.CASCADE, related_name="points_scale")
    placement = models.PositiveIntegerField(_("Placement"))
    points = models.PositiveIntegerField(_("Points"))

    class Meta:
        ordering = ["category", "placement"]
        constraints = [
            models.UniqueConstraint(fields=["category", "placement"], name="unique_placement_per_category"),
        ]
        verbose_name = _("Ranking points scale entry")
        verbose_name_plural = _("Ranking points scale")

    def __str__(self):
        return f"{self.category}: #{self.placement} = {self.points}"


class PlayerRanking(models.Model):
    """A player's current standing in one RankingCategory.

    Distinct from tournament Standings (apps.tournaments.services.standings),
    which rank participants within a single competition/group — this
    accumulates across every tournament a player has competed in.
    """

    player = models.ForeignKey("players.Player", on_delete=models.CASCADE, related_name="rankings")
    category = models.ForeignKey(RankingCategory, on_delete=models.CASCADE, related_name="player_rankings")
    points = models.PositiveIntegerField(_("Points"), default=0)
    previous_rank = models.PositiveIntegerField(_("Previous rank"), null=True, blank=True)
    current_rank = models.PositiveIntegerField(_("Current rank"), null=True, blank=True)
    tournaments_played = models.PositiveIntegerField(_("Tournaments played"), default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "-points", "player"]
        constraints = [
            models.UniqueConstraint(fields=["player", "category"], name="unique_ranking_per_player_and_category"),
        ]
        indexes = [
            models.Index(fields=["category", "current_rank"]),
        ]
        verbose_name = _("Player ranking")

    def __str__(self):
        return f"{self.player} — {self.category}: {self.points}"

    @property
    def rank_change(self):
        """Positive means the player moved up (lower rank number is better)."""
        if self.previous_rank is None or self.current_rank is None:
            return None
        return self.previous_rank - self.current_rank


class EloRating(models.Model):
    """A player's live Elo rating in one RankingCategory.

    Distinct from PlayerRanking (placement-based points awarded once a
    competition finishes, see apps.rankings.services.award_ranking_points):
    this updates after every individual completed match, per standard
    table-tennis Elo rules (apps.rankings.elo). The two systems intentionally
    coexist — CLAUDE.md section 19 keeps tournament standings, placement
    points and any future ranking algorithm as separate, independently
    evolvable concepts.
    """

    player = models.ForeignKey("players.Player", on_delete=models.CASCADE, related_name="elo_ratings")
    category = models.ForeignKey(RankingCategory, on_delete=models.CASCADE, related_name="elo_ratings")
    rating = models.FloatField(_("Rating"), default=1500.0)
    matches_played = models.PositiveIntegerField(_("Matches played"), default=0)
    previous_rank = models.PositiveIntegerField(_("Previous rank"), null=True, blank=True)
    current_rank = models.PositiveIntegerField(_("Current rank"), null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "-rating", "player"]
        constraints = [
            models.UniqueConstraint(fields=["player", "category"], name="unique_elo_rating_per_player_and_category"),
        ]
        indexes = [
            models.Index(fields=["category", "current_rank"]),
        ]
        verbose_name = _("Elo rating")

    def __str__(self):
        return f"{self.player} — {self.category}: {round(self.rating)}"

    @property
    def rank_change(self):
        if self.previous_rank is None or self.current_rank is None:
            return None
        return self.previous_rank - self.current_rank


class EloRatingEvent(models.Model):
    """Audit trail entry for one match's effect on one player's Elo rating.

    Kept separate from EloRating (which only holds the running total) for
    the same reason as RankingEvent (CLAUDE.md section 33), and additionally
    so a later correction to the match result can be reversed: apps.rankings
    elo.sync_elo_ratings finds a match's existing events, undoes their
    rating_before/rating_after delta, deletes them, then re-applies the
    match's current result if it's still in a ratable state.
    """

    match = models.ForeignKey("matches.Match", on_delete=models.CASCADE, related_name="elo_events")
    player = models.ForeignKey("players.Player", on_delete=models.CASCADE, related_name="elo_events")
    category = models.ForeignKey(RankingCategory, on_delete=models.CASCADE, related_name="elo_events")
    opponent_participant = models.ForeignKey(
        "tournaments.Participant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    won = models.BooleanField(_("Won"))
    rating_before = models.FloatField(_("Rating before"))
    rating_after = models.FloatField(_("Rating after"))
    delta = models.FloatField(_("Delta"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["match", "player"], name="unique_elo_event_per_match_and_player"),
        ]
        verbose_name = _("Elo rating event")

    def __str__(self):
        return f"{self.player} — {self.match}: {self.delta:+.1f}"


class RankingEvent(models.Model):
    """Audit trail entry for one award of ranking points to one player.

    Kept separate from PlayerRanking (which only holds the running total) so
    every points change is traceable back to the competition and placement
    that caused it (CLAUDE.md section 33). The unique constraint makes
    awarding idempotent: re-running the award for a competition that has
    already been scored is a no-op rather than double-counting.
    """

    player = models.ForeignKey("players.Player", on_delete=models.CASCADE, related_name="ranking_events")
    category = models.ForeignKey(RankingCategory, on_delete=models.CASCADE, related_name="events")
    competition = models.ForeignKey(
        "tournaments.Competition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ranking_events",
    )
    placement = models.PositiveIntegerField(_("Placement"))
    points_awarded = models.PositiveIntegerField(_("Points awarded"))
    points_before = models.PositiveIntegerField(_("Points before"))
    points_after = models.PositiveIntegerField(_("Points after"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["player", "category", "competition"], name="unique_ranking_event_per_player_and_competition"
            ),
        ]
        verbose_name = _("Ranking event")

    def __str__(self):
        return f"{self.player} — {self.category}: #{self.placement} ({self.points_awarded:+d})"
