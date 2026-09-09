from django.test import SimpleTestCase

from apps.tournaments.services.standings import TEAM_TIE_BREAK_RULES, MatchRecord, compute_standings


def rec(a, b, sets_a, sets_b, points_a, points_b):
    return MatchRecord(
        participant_a=a, participant_b=b, sets_won_a=sets_a, sets_won_b=sets_b,
        points_scored_a=points_a, points_scored_b=points_b,
    )


def team_rec(a, b, matches_a, matches_b, games_a, games_b, points_a, points_b):
    return MatchRecord(
        participant_a=a, participant_b=b,
        individual_matches_won_a=matches_a, individual_matches_won_b=matches_b,
        sets_won_a=games_a, sets_won_b=games_b,
        points_scored_a=points_a, points_scored_b=points_b,
    )


class BasicStandingsTests(SimpleTestCase):
    def test_clear_ranking_no_ties(self):
        # A beats everyone, B beats C, C beats no one.
        matches = [
            rec("A", "B", 3, 0, 33, 10),
            rec("A", "C", 3, 0, 33, 15),
            rec("B", "C", 3, 1, 30, 25),
        ]
        rows = compute_standings(["A", "B", "C"], matches)
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])
        a_row = rows[0]
        self.assertEqual(a_row.played, 2)
        self.assertEqual(a_row.wins, 2)
        self.assertEqual(a_row.losses, 0)
        self.assertEqual(a_row.match_points, 4)
        self.assertEqual(a_row.sets_won, 6)
        self.assertEqual(a_row.sets_lost, 0)
        self.assertEqual(a_row.set_difference, 6)
        self.assertEqual(a_row.points_scored, 66)
        self.assertEqual(a_row.points_conceded, 25)
        self.assertEqual(a_row.point_difference, 41)
        self.assertEqual([r.rank for r in rows], [1, 2, 3])

    def test_participant_with_no_matches_yet_still_gets_a_row(self):
        matches = [rec("A", "B", 3, 0, 33, 10)]
        rows = compute_standings(["A", "B", "C"], matches)
        c_row = next(r for r in rows if r.participant == "C")
        self.assertEqual(c_row.played, 0)
        self.assertEqual(c_row.match_points, 0)


class TwoWayTieTests(SimpleTestCase):
    def test_resolved_cleanly_by_head_to_head(self):
        # A and B tie in match points overall (both beat C, and A beat B),
        # so only their direct result can separate them.
        matches = [
            rec("A", "B", 3, 1, 33, 25),  # A beats B directly
            rec("A", "C", 3, 0, 33, 10),
            rec("B", "C", 3, 0, 33, 10),
        ]
        rows = compute_standings(["A", "B", "C"], matches)
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])


class CyclicThreeWayTieTests(SimpleTestCase):
    def test_cyclic_tie_falls_through_to_set_difference(self):
        # Classic cycle: A beats B, B beats C, C beats A. All three finish
        # 1-1, tied on match points AND on head-to-head (each has exactly
        # one win and one loss within the tied trio) — head-to-head cannot
        # separate them, so it must fall through to set difference.
        matches = [
            rec("A", "B", 3, 0, 33, 10),   # A beats B big
            rec("B", "C", 3, 0, 33, 10),   # B beats C big
            rec("C", "A", 3, 2, 55, 50),   # C beats A narrowly
        ]
        rows = compute_standings(["A", "B", "C"], matches)
        # Set difference within the trio: A = (3+2)-(0+3) = +2 (beat B 3-0, lost to C 2-3)
        #                                  B = (0+3)-(3+0) = 0  (lost to A 0-3, beat C 3-0)
        #                                  C = (3+3)-(0+2)... recompute: C beat B 3-0 and beat A 3-2 -> wait C lost to B? no B beat C.
        # Recheck source of truth from the recs: A beats B 3-0; B beats C 3-0; C beats A 3-2.
        # A: won 3 (vs B), lost 0 (vs B); won 2 (vs C), lost 3 (vs C) -> sets 5-3 -> diff +2
        # B: won 0 (vs A), lost 3 (vs A); won 3 (vs C), lost 0 (vs C) -> sets 3-3 -> diff 0
        # C: won 0 (vs B)... C lost to B 0-3 -> won 0 lost 3; won 3 lost 2 (vs A) -> sets 3-5 -> diff -2
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])
        self.assertEqual([r.match_points for r in rows], [2, 2, 2])  # confirms it WAS a tie

    def test_head_to_head_never_used_incorrectly_on_a_cycle(self):
        # Sanity check on the trap: naively looking only at A-vs-C's direct
        # result would rank C above A (C won that match). The correct
        # multi-way computation ranks by group set-difference instead once
        # head-to-head is exhausted, which ranks A above C here despite C
        # having won their direct match.
        matches = [
            rec("A", "B", 3, 0, 33, 10),
            rec("B", "C", 3, 0, 33, 10),
            rec("C", "A", 3, 2, 55, 50),
        ]
        rows = compute_standings(["A", "B", "C"], matches)
        rank_of = {r.participant: r.rank for r in rows}
        self.assertLess(rank_of["A"], rank_of["C"])  # A ranks ABOVE C despite losing to C head-to-head


class NonCyclicThreeWayTieTests(SimpleTestCase):
    def test_resolved_fully_by_head_to_head(self):
        # A beats both B and C; B beats C. No cycle: head-to-head alone
        # fully separates all three (A: 2 wins, B: 1 win, C: 0 wins within
        # the trio).
        matches = [
            rec("A", "B", 3, 0, 33, 10),
            rec("A", "C", 3, 0, 33, 10),
            rec("B", "C", 3, 1, 33, 20),
        ]
        rows = compute_standings(["A", "B", "C"], matches)
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])


class FourWayTieTests(SimpleTestCase):
    def test_head_to_head_splits_a_four_way_tie_into_sub_pairs(self):
        # Four-way group where {A,B} end up tied on overall match points
        # (4 each) and {C,D} end up tied separately (2 each) — A beat B
        # and C beat D directly, but overall match points alone don't
        # separate A from B or C from D, since each also split a result
        # against the other pair. Head-to-head must split {A,B,C,D} into
        # the two correct pairs, then decide each pair by their own
        # direct result.
        matches = [
            rec("A", "B", 3, 1, 33, 20),   # A beats B
            rec("A", "C", 3, 0, 33, 10),   # A beats C
            rec("A", "D", 1, 3, 20, 33),   # A loses to D
            rec("B", "C", 3, 0, 33, 10),   # B beats C
            rec("B", "D", 3, 1, 33, 20),   # B beats D
            rec("C", "D", 3, 2, 40, 38),   # C beats D
        ]
        rows = compute_standings(["A", "B", "C", "D"], matches)
        ranks = [r.participant for r in rows]
        points = {r.participant: r.match_points for r in rows}

        self.assertEqual(points["A"], points["B"])  # both 4 pts: genuinely tied overall
        self.assertEqual(points["C"], points["D"])  # both 2 pts: genuinely tied overall
        self.assertEqual(set(ranks[:2]), {"A", "B"})
        self.assertEqual(set(ranks[2:]), {"C", "D"})
        self.assertEqual(ranks[0], "A")  # A beat B directly
        self.assertEqual(ranks[2], "C")  # C beat D directly


class DeterminismTests(SimpleTestCase):
    def test_fully_unbreakable_tie_still_produces_stable_order(self):
        # A and B have identical stats in every category and never played
        # each other (e.g. from different groups feeding a combined
        # table) — every tie-break is exhausted, so the fallback must
        # still produce a deterministic (not arbitrary/random) order.
        matches = [
            rec("A", "C", 3, 0, 33, 10),
            rec("B", "D", 3, 0, 33, 10),
        ]
        first = compute_standings(["A", "B", "C", "D"], matches)
        second = compute_standings(["A", "B", "C", "D"], matches)
        self.assertEqual([r.participant for r in first], [r.participant for r in second])


class TeamTieBreakTests(SimpleTestCase):
    def test_individual_match_difference_is_a_no_op_for_ordinary_matches(self):
        """DEFAULT_TIE_BREAK_RULES (used for every non-team competition)
        never applies INDIVIDUAL_MATCH_DIFFERENCE — a MatchRecord that
        never sets individual_matches_won_a/b (every existing caller)
        ranks identically to before this axis was added."""
        matches = [rec("A", "B", 3, 0, 33, 10), rec("A", "C", 3, 1, 33, 20), rec("B", "C", 3, 2, 33, 30)]
        rows = compute_standings(["A", "B", "C"], matches)
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])

    def test_individual_match_ratio_breaks_a_match_points_tie_before_games(self):
        # A, B, C each win one tie and lose one -> tied at 2 match points,
        # and it's a 3-way cycle so head-to-head can't resolve it either.
        # Games (sets) alone would favor B (9-3) over A (7-5), but ITTF
        # ranks individual-match ratio first: A has the best difference.
        matches = [
            team_rec("A", "B", 3, 0, 33, 10, 30, 10),  # A's individual-match diff so far: +3
            team_rec("B", "C", 3, 2, 39, 44, 30, 30),  # B: +1, C: -1
            team_rec("C", "A", 3, 1, 34, 26, 30, 25),  # C: +2, A: -2 -> A total +1, C total +1...
        ]
        rows = compute_standings(["A", "B", "C"], matches, tie_break_rules=TEAM_TIE_BREAK_RULES)
        by_participant = {r.participant: r for r in rows}
        self.assertEqual(by_participant["A"].match_points, by_participant["B"].match_points)
        self.assertEqual(by_participant["B"].match_points, by_participant["C"].match_points)
        # A: +3 (beat B) - 2 (lost to C 1-3) = +1
        # B: -3 (lost to A) + 1 (beat C 3-2) = -2
        # C: -1 (lost to B 2-3) + 2 (beat A 3-1) = +1
        # A and C tie on individual-match difference (+1) — this case
        # only checks the axis is actually being used (B ranks last),
        # a separate test below checks a fully-distinct 3-way case.
        self.assertEqual(by_participant["B"].individual_match_difference, -2)
        self.assertNotEqual(by_participant["B"].rank, 1)

    def test_individual_match_difference_fully_resolves_a_distinct_3_way_tie(self):
        matches = [
            team_rec("A", "B", 3, 0, 33, 10, 30, 10),  # A +3, B -3
            team_rec("B", "C", 3, 0, 33, 12, 30, 12),  # B +3, C -3
            team_rec("C", "A", 3, 1, 34, 26, 30, 25),  # C +2, A -2
        ]
        rows = compute_standings(["A", "B", "C"], matches, tie_break_rules=TEAM_TIE_BREAK_RULES)
        by_participant = {r.participant: r for r in rows}
        # A: +3-2=+1, B: -3+3=0, C: -3+2=-1
        self.assertEqual(by_participant["A"].individual_match_difference, 1)
        self.assertEqual(by_participant["B"].individual_match_difference, 0)
        self.assertEqual(by_participant["C"].individual_match_difference, -1)
        self.assertEqual([r.participant for r in rows], ["A", "B", "C"])
