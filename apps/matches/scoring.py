"""Set score validation and match-result computation.

Kept separate from Django's ORM (no Match/MatchSet imports here) so the
core business rules — what makes a set score valid, when a match is
decided — are unit-testable without a database, and reusable regardless of
how a score arrives (form, API, live-scoring HTMX endpoint, ...).

Only django.utils.translation is used, for user-facing error text — that
doesn't require a request/database and doesn't compromise testability.
"""

from dataclasses import dataclass
from typing import Optional

from django.utils.translation import gettext_lazy as _


class ScoreValidationError(ValueError):
    pass


def validate_set_score(participant_a_score: int, participant_b_score: int, *, points_to_win: int, win_by: int, cap_at: Optional[int] = None) -> None:
    """Raise ScoreValidationError if the set score is not a valid final score.

    Rules: a set can't end tied; the winner must reach at least
    points_to_win; the winning margin must be at least win_by UNLESS an
    optional hard cap has been reached (a cap always ends the set
    regardless of margin, e.g. a sudden-death cap at 21).
    """
    if participant_a_score < 0 or participant_b_score < 0:
        raise ScoreValidationError(_("Scores cannot be negative."))

    if participant_a_score == participant_b_score:
        raise ScoreValidationError(_("A set cannot end in a tie."))

    winner_score = max(participant_a_score, participant_b_score)
    loser_score = min(participant_a_score, participant_b_score)

    if winner_score < points_to_win:
        raise ScoreValidationError(
            _("The winning score must be at least %(points)s.") % {"points": points_to_win}
        )

    if cap_at is not None:
        if winner_score > cap_at:
            raise ScoreValidationError(_("The winning score cannot exceed %(cap)s.") % {"cap": cap_at})
        if winner_score == cap_at:
            return  # the hard cap always ends the set, regardless of margin

    if winner_score - loser_score < win_by:
        raise ScoreValidationError(
            _("The winning margin must be at least %(margin)s points.") % {"margin": win_by}
        )


def sets_to_win(best_of_sets: int) -> int:
    return best_of_sets // 2 + 1


@dataclass(frozen=True)
class MatchResult:
    sets_won_a: int
    sets_won_b: int
    is_complete: bool
    winner: Optional[str]  # "a", "b", or None


def compute_match_result(set_scores: list[tuple[int, int]], *, best_of_sets: int) -> MatchResult:
    """Determine the match result from a list of (a_score, b_score) sets."""
    needed = sets_to_win(best_of_sets)
    sets_won_a = sum(1 for a, b in set_scores if a > b)
    sets_won_b = sum(1 for a, b in set_scores if b > a)

    if sets_won_a >= needed:
        return MatchResult(sets_won_a, sets_won_b, True, "a")
    if sets_won_b >= needed:
        return MatchResult(sets_won_a, sets_won_b, True, "b")
    return MatchResult(sets_won_a, sets_won_b, False, None)
