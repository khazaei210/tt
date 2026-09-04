from django.test import SimpleTestCase

from apps.matches.scoring import (
    MatchResult,
    ScoreValidationError,
    compute_match_result,
    sets_to_win,
    validate_set_score,
)


class ValidateSetScoreTests(SimpleTestCase):
    def test_valid_standard_scores(self):
        valid_cases = [(11, 0), (11, 5), (11, 9), (0, 11), (9, 11)]
        for a, b in valid_cases:
            with self.subTest(a=a, b=b):
                validate_set_score(a, b, points_to_win=11, win_by=2)  # should not raise

    def test_deuce_scores_valid_with_correct_margin(self):
        for a, b in [(12, 10), (13, 11), (20, 18), (15, 13)]:
            with self.subTest(a=a, b=b):
                validate_set_score(a, b, points_to_win=11, win_by=2)

    def test_tied_score_rejected(self):
        with self.assertRaises(ScoreValidationError):
            validate_set_score(10, 10, points_to_win=11, win_by=2)

    def test_negative_score_rejected(self):
        with self.assertRaises(ScoreValidationError):
            validate_set_score(-1, 11, points_to_win=11, win_by=2)

    def test_winner_below_points_to_win_rejected(self):
        with self.assertRaises(ScoreValidationError):
            validate_set_score(10, 8, points_to_win=11, win_by=2)

    def test_insufficient_margin_rejected(self):
        # 11-10 reaches 11 but margin is only 1.
        with self.assertRaises(ScoreValidationError):
            validate_set_score(11, 10, points_to_win=11, win_by=2)

    def test_insufficient_margin_rejected_in_deuce(self):
        # 12-11 reaches past 11 but margin is only 1; should have continued to 13-11.
        with self.assertRaises(ScoreValidationError):
            validate_set_score(12, 11, points_to_win=11, win_by=2)

    def test_hard_cap_valid_regardless_of_margin(self):
        # Cap at 21: a 21-20 finish is valid even though margin < win_by.
        validate_set_score(21, 20, points_to_win=11, win_by=2, cap_at=21)

    def test_score_exceeding_cap_rejected(self):
        with self.assertRaises(ScoreValidationError):
            validate_set_score(22, 20, points_to_win=11, win_by=2, cap_at=21)

    def test_below_cap_still_requires_normal_margin(self):
        # Below the cap, the normal win-by-2 rule still applies.
        with self.assertRaises(ScoreValidationError):
            validate_set_score(20, 19, points_to_win=11, win_by=2, cap_at=21)

    def test_win_by_one_rule(self):
        # Some formats use win-by-1 (first to N wins outright); verify the
        # parameter is actually respected, not hardcoded to 2.
        validate_set_score(11, 10, points_to_win=11, win_by=1)
        with self.assertRaises(ScoreValidationError):
            validate_set_score(10, 9, points_to_win=11, win_by=1)  # winner below points_to_win


class SetsToWinTests(SimpleTestCase):
    def test_known_values(self):
        self.assertEqual(sets_to_win(3), 2)
        self.assertEqual(sets_to_win(5), 3)
        self.assertEqual(sets_to_win(7), 4)


class ComputeMatchResultTests(SimpleTestCase):
    def test_incomplete_match(self):
        result = compute_match_result([(11, 5), (9, 11)], best_of_sets=5)
        self.assertEqual(result, MatchResult(sets_won_a=1, sets_won_b=1, is_complete=False, winner=None))

    def test_participant_a_wins_best_of_five_by_sweep(self):
        result = compute_match_result([(11, 5), (11, 8), (11, 9)], best_of_sets=5)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.winner, "a")
        self.assertEqual((result.sets_won_a, result.sets_won_b), (3, 0))

    def test_participant_b_wins_best_of_five_after_five_sets(self):
        sets = [(11, 5), (9, 11), (11, 8), (7, 11), (8, 11)]
        result = compute_match_result(sets, best_of_sets=5)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.winner, "b")
        self.assertEqual((result.sets_won_a, result.sets_won_b), (2, 3))

    def test_best_of_three_decided_after_two_sets(self):
        result = compute_match_result([(11, 3), (11, 7)], best_of_sets=3)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.winner, "a")

    def test_no_sets_played_yet(self):
        result = compute_match_result([], best_of_sets=5)
        self.assertFalse(result.is_complete)
        self.assertIsNone(result.winner)

    def test_extra_sets_beyond_decision_do_not_change_winner(self):
        # Defensive: even if an extra set were appended after the match was
        # already decided, the winner computation remains stable.
        result = compute_match_result([(11, 5), (11, 8), (11, 9), (5, 11)], best_of_sets=5)
        self.assertTrue(result.is_complete)
        self.assertEqual(result.winner, "a")
