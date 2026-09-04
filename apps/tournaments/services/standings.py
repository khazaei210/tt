"""Round-robin standings computation with configurable, multi-way-safe tie-breaks.

Pure and framework-agnostic, like round_robin.py and knockout.py — operates
on plain participant identifiers and MatchRecord summaries, no ORM.

The one correctness trap this has to avoid (flagged explicitly in the
project's own domain notes): when 3+ participants are tied, you cannot
resolve it with a single pairwise head-to-head lookup — a 3-way cycle
(A beat B, B beat C, C beat A) has no pairwise winner, and even a
non-cyclic 3+ way tie needs a proper mini-table, not one match result.

The approach: every tie-break criterion — including head-to-head — is
evaluated using stats recomputed from ONLY the matches played among the
currently-tied subgroup, not the full group. Head-to-head is simply "match
points computed within the subgroup's own mutual matches" rather than a
special pairwise case, which makes it correct for cyclic and non-cyclic
ties alike. When a criterion still leaves a tie, the group narrows and the
NEXT criterion is tried — but a criterion already used is never reapplied
to the narrower subgroup (reapplying head-to-head to two participants
remaining from a larger tied group is exactly the naive-pairwise mistake
this design avoids: it can rank two participants opposite to how the
group-wide picture actually looks, e.g. A beat B head-to-head but both
still end up mid-table tied by every group-relative measure).
"""

from dataclasses import dataclass, field
from typing import Any, Hashable, Optional

POINTS_PER_WIN = 2
POINTS_PER_LOSS = 0

HEAD_TO_HEAD = "head_to_head"
SET_DIFFERENCE = "set_difference"
POINT_DIFFERENCE = "point_difference"
POINTS_SCORED = "points_scored"

DEFAULT_TIE_BREAK_RULES = (HEAD_TO_HEAD, SET_DIFFERENCE, POINT_DIFFERENCE, POINTS_SCORED)


@dataclass(frozen=True)
class MatchRecord:
    participant_a: Hashable
    participant_b: Hashable
    sets_won_a: int
    sets_won_b: int
    points_scored_a: int
    points_scored_b: int


@dataclass
class _Stats:
    played: int = 0
    wins: int = 0
    losses: int = 0
    match_points: int = 0
    sets_won: int = 0
    sets_lost: int = 0
    points_scored: int = 0
    points_conceded: int = 0

    @property
    def set_difference(self) -> int:
        return self.sets_won - self.sets_lost

    @property
    def point_difference(self) -> int:
        return self.points_scored - self.points_conceded


@dataclass(frozen=True)
class StandingsRow:
    participant: Any
    rank: int
    played: int
    wins: int
    losses: int
    match_points: int
    sets_won: int
    sets_lost: int
    set_difference: int
    points_scored: int
    points_conceded: int
    point_difference: int


_METRIC_EXTRACTORS = {
    HEAD_TO_HEAD: lambda s: s.match_points,
    SET_DIFFERENCE: lambda s: s.set_difference,
    POINT_DIFFERENCE: lambda s: s.point_difference,
    POINTS_SCORED: lambda s: s.points_scored,
}


def _apply_match(stats: dict, m: MatchRecord) -> None:
    a, b = m.participant_a, m.participant_b
    sa, sb = stats[a], stats[b]

    sa.played += 1
    sb.played += 1
    sa.sets_won += m.sets_won_a
    sa.sets_lost += m.sets_won_b
    sb.sets_won += m.sets_won_b
    sb.sets_lost += m.sets_won_a
    sa.points_scored += m.points_scored_a
    sa.points_conceded += m.points_scored_b
    sb.points_scored += m.points_scored_b
    sb.points_conceded += m.points_scored_a

    if m.sets_won_a > m.sets_won_b:
        sa.wins += 1
        sa.match_points += POINTS_PER_WIN
        sb.losses += 1
        sb.match_points += POINTS_PER_LOSS
    else:
        sb.wins += 1
        sb.match_points += POINTS_PER_WIN
        sa.losses += 1
        sa.match_points += POINTS_PER_LOSS


def _build_stats_for_subset(participant_ids, matches) -> dict:
    id_set = set(participant_ids)
    stats = {pid: _Stats() for pid in participant_ids}
    for m in matches:
        if m.participant_a in id_set and m.participant_b in id_set:
            _apply_match(stats, m)
    return stats


def _rank_group(participant_ids, matches, rules) -> list:
    """Order participant_ids (best first) by recursively applying rules,
    each evaluated on stats restricted to the current subgroup's own
    mutual matches. Falls back to a stable (identity-based) order for any
    tie that survives every configured rule, so the result is always fully
    deterministic."""
    if len(participant_ids) <= 1:
        return list(participant_ids)

    if not rules:
        return sorted(participant_ids, key=repr)

    stats = _build_stats_for_subset(participant_ids, matches)
    metric = _METRIC_EXTRACTORS[rules[0]]

    buckets: dict = {}
    for pid in participant_ids:
        buckets.setdefault(metric(stats[pid]), []).append(pid)

    ordered = []
    for key in sorted(buckets.keys(), reverse=True):
        group = buckets[key]
        if len(group) == 1:
            ordered.extend(group)
        else:
            ordered.extend(_rank_group(group, matches, rules[1:]))
    return ordered


def compute_standings(
    participant_ids: list[Hashable],
    matches: list[MatchRecord],
    *,
    tie_break_rules: Optional[tuple] = None,
) -> list[StandingsRow]:
    """Compute ranked standings for a round-robin group.

    participant_ids: every participant in the group (including anyone with
        zero completed matches so far — they still get a row).
    matches: completed match results only; incomplete matches shouldn't be
        passed in, since standings reflect decided results.
    tie_break_rules: ordered sequence of criteria to break ties on equal
        match points, restricted to the tied subgroup at each step
        (defaults to head-to-head, set difference, point difference,
        points scored — see module docstring for why restriction matters).
    """
    rules = tuple(tie_break_rules) if tie_break_rules is not None else DEFAULT_TIE_BREAK_RULES
    overall_stats = _build_stats_for_subset(participant_ids, matches)

    buckets: dict = {}
    for pid in participant_ids:
        buckets.setdefault(overall_stats[pid].match_points, []).append(pid)

    ranked_ids = []
    for match_points in sorted(buckets.keys(), reverse=True):
        group = buckets[match_points]
        if len(group) == 1:
            ranked_ids.append(group[0])
        else:
            ranked_ids.extend(_rank_group(group, matches, list(rules)))

    rows = []
    for rank, pid in enumerate(ranked_ids, start=1):
        s = overall_stats[pid]
        rows.append(
            StandingsRow(
                participant=pid,
                rank=rank,
                played=s.played,
                wins=s.wins,
                losses=s.losses,
                match_points=s.match_points,
                sets_won=s.sets_won,
                sets_lost=s.sets_lost,
                set_difference=s.set_difference,
                points_scored=s.points_scored,
                points_conceded=s.points_conceded,
                point_difference=s.point_difference,
            )
        )
    return rows
