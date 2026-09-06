"""Live Elo rating updates, applied after each individual match completes.

Distinct from apps.rankings.services (placement-based points awarded once a
whole competition finishes, CLAUDE.md section 19): this module updates a
player's EloRating after every match with a genuine, played result, using
the standard Elo formula as commonly adapted by table-tennis rating bodies
(e.g. USATT/ITTF-style K-factor bands — CLAUDE.md section 16 wants such
rules represented explicitly, not hard-coded inline, so they live here as
named constants/functions rather than scattered through the app).

Design decisions worth knowing before changing this file:

- Only MatchStatus.COMPLETED and MatchStatus.RETIRED are rated — both
  involve actual play with a genuine winner. WALKOVER and DEFAULT don't
  (CLAUDE.md doesn't specify this, but rating a match nobody played is not
  a reasonable default, mirroring how most real rating systems exclude
  no-shows).
- Only INDIVIDUAL and DOUBLES participants are rated, same scope as
  apps.rankings.services.award_ranking_points. Team competitions are
  skipped: how a team result should move individual players' ratings isn't
  specified anywhere (CLAUDE.md section 35: don't assume unstated rules).
- For doubles, both players' *own* ratings are used to compute an average
  "side rating" for the expected-score calculation, and each player's own
  rating/matches_played then determines their own K-factor and delta. This
  is a common, reasonable extension of singles Elo to pairs — not an
  official ITTF doubles-rating spec (none is referenced in CLAUDE.md).
- A competition must have a ranking_category configured (same field
  award_ranking_points uses) or its matches are left unrated entirely.
- sync_elo_ratings() is idempotent and correction-safe: it always reverses
  any EloRatingEvents already recorded for the match (by subtracting their
  stored delta back out and decrementing matches_played) before applying a
  fresh rating change for the match's *current* result, if any. This is a
  simple reversal, not a full historical replay — if other matches were
  rated in between, the reversal is only an approximation of what ratings
  would look like had the corrected match never happened. That's an
  accepted, documented trade-off for a correction path that's meant to be
  rare (CLAUDE.md section 33: traceable, not necessarily a perfect replay).
"""

from django.db import transaction

from .models import EloRating, EloRatingEvent, RankingCategory
from .services import players_for_participant

DEFAULT_ELO_RATING = 1500.0

# Below this many rated matches a player's rating is "provisional" and moves
# faster, so it converges toward a true skill level quickly instead of being
# dragged down by early results for a long time.
PROVISIONAL_MATCHES_THRESHOLD = 30
PROVISIONAL_K_FACTOR = 40
HIGH_RATING_THRESHOLD = 2400
HIGH_RATING_K_FACTOR = 16
STANDARD_K_FACTOR = 24


def k_factor(rating, matches_played):
    if matches_played < PROVISIONAL_MATCHES_THRESHOLD:
        return PROVISIONAL_K_FACTOR
    if rating >= HIGH_RATING_THRESHOLD:
        return HIGH_RATING_K_FACTOR
    return STANDARD_K_FACTOR


def expected_score(rating, opponent_rating):
    """Probability `rating` beats `opponent_rating`, per the standard Elo curve."""
    return 1.0 / (1.0 + 10 ** ((opponent_rating - rating) / 400.0))


# Match statuses that reflect a genuinely played result, per the module
# docstring above.
RATABLE_MATCH_STATUSES = ("completed", "retired")


def _reverse_existing_events(match):
    for event in EloRatingEvent.objects.filter(match=match).select_related("player"):
        rating = EloRating.objects.get(player=event.player, category=event.category)
        rating.rating -= event.delta
        rating.matches_played = max(rating.matches_played - 1, 0)
        rating.save(update_fields=["rating", "matches_played", "updated_at"])
        event.delete()


def _rate_side(match, category, side_players, side_rating_avg, opponent_rating_avg, won, opponent_participant):
    for player in side_players:
        rating, _created = EloRating.objects.get_or_create(
            player=player, category=category, defaults={"rating": DEFAULT_ELO_RATING}
        )
        expected = expected_score(side_rating_avg, opponent_rating_avg)
        k = k_factor(rating.rating, rating.matches_played)
        delta = k * ((1.0 if won else 0.0) - expected)

        rating_before = rating.rating
        rating.rating = rating_before + delta
        rating.matches_played += 1
        rating.save(update_fields=["rating", "matches_played", "updated_at"])

        EloRatingEvent.objects.create(
            match=match,
            player=player,
            category=category,
            opponent_participant=opponent_participant,
            won=won,
            rating_before=rating_before,
            rating_after=rating.rating,
            delta=delta,
        )


@transaction.atomic
def sync_elo_ratings(match):
    """Reconcile a match's Elo effect with its current result.

    Safe to call after any change to `match.status`/`match.winner` —
    normal progress, a correction, or an undo back to an unratable state.
    Returns the list of newly created EloRatingEvents (empty if the match
    ended up unrated, e.g. no ranking_category, a BYE, or a team match).
    """
    _reverse_existing_events(match)

    if match.status not in RATABLE_MATCH_STATUSES or match.winner_id is None:
        return []
    if match.is_bye or match.participant_a_id is None or match.participant_b_id is None:
        return []

    category = match.competition.ranking_category
    if category is None:
        return []

    participant_a = match.participant_a
    participant_b = match.participant_b
    players_a = players_for_participant(participant_a)
    players_b = players_for_participant(participant_b)
    if not players_a or not players_b:
        return []

    ratings_a = [
        EloRating.objects.get_or_create(player=p, category=category, defaults={"rating": DEFAULT_ELO_RATING})[0].rating
        for p in players_a
    ]
    ratings_b = [
        EloRating.objects.get_or_create(player=p, category=category, defaults={"rating": DEFAULT_ELO_RATING})[0].rating
        for p in players_b
    ]
    avg_a = sum(ratings_a) / len(ratings_a)
    avg_b = sum(ratings_b) / len(ratings_b)

    a_won = match.winner_id == participant_a.id
    events_before = set(EloRatingEvent.objects.filter(match=match).values_list("pk", flat=True))

    _rate_side(match, category, players_a, avg_a, avg_b, a_won, opponent_participant=participant_b)
    _rate_side(match, category, players_b, avg_b, avg_a, not a_won, opponent_participant=participant_a)

    _recompute_elo_ranks(category)
    return list(EloRatingEvent.objects.filter(match=match).exclude(pk__in=events_before))


def _recompute_elo_ranks(category: RankingCategory):
    ratings = list(EloRating.objects.filter(category=category).order_by("-rating", "player_id"))
    for index, rating in enumerate(ratings, start=1):
        if rating.current_rank == index:
            continue
        rating.previous_rank = rating.current_rank
        rating.current_rank = index
        rating.save(update_fields=["previous_rank", "current_rank"])
