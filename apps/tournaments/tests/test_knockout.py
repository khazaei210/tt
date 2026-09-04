from django.test import SimpleTestCase

from apps.tournaments.services.knockout import (
    generate_knockout_bracket,
    next_power_of_two,
    seed_positions,
)


class NextPowerOfTwoTests(SimpleTestCase):
    def test_known_values(self):
        cases = {1: 1, 2: 2, 3: 4, 4: 4, 5: 8, 8: 8, 9: 16, 10: 16, 16: 16, 17: 32}
        for n, expected in cases.items():
            with self.subTest(n=n):
                self.assertEqual(next_power_of_two(n), expected)


class SeedPositionsTests(SimpleTestCase):
    def test_known_small_sizes(self):
        self.assertEqual(seed_positions(1), [1])
        self.assertEqual(seed_positions(2), [1, 2])
        self.assertEqual(seed_positions(4), [1, 4, 2, 3])
        self.assertEqual(seed_positions(8), [1, 8, 4, 5, 2, 7, 3, 6])

    def test_rejects_non_power_of_two(self):
        for bad_size in (0, 3, 5, 6, 7, 9):
            with self.subTest(bad_size=bad_size):
                with self.assertRaises(ValueError):
                    seed_positions(bad_size)

    def test_is_a_permutation_of_seed_ranks(self):
        for size in (2, 4, 8, 16, 32):
            with self.subTest(size=size):
                positions = seed_positions(size)
                self.assertEqual(sorted(positions), list(range(1, size + 1)))

    def test_seed_one_and_two_are_in_different_halves(self):
        for size in (2, 4, 8, 16, 32):
            with self.subTest(size=size):
                positions = seed_positions(size)
                half = size // 2
                pos_of_1 = positions.index(1)
                pos_of_2 = positions.index(2)
                self.assertNotEqual(pos_of_1 // half, pos_of_2 // half)

    def test_seeds_one_to_four_are_one_per_quarter(self):
        for size in (4, 8, 16, 32):
            with self.subTest(size=size):
                positions = seed_positions(size)
                quarter = size // 4
                quarters = [positions[i * quarter:(i + 1) * quarter] for i in range(4)]
                for seed in (1, 2, 3, 4):
                    containing = [q for q in quarters if seed in q]
                    self.assertEqual(len(containing), 1)


class KnockoutBracketRoundOneTests(SimpleTestCase):
    def test_power_of_two_counts_have_no_byes(self):
        for n in (2, 4, 8, 16):
            with self.subTest(n=n):
                bracket = generate_knockout_bracket(list(range(n)))
                self.assertEqual(bracket.bracket_size, n)
                round1 = [m for m in bracket.matches if m.round_number == 1]
                self.assertTrue(all(not m.is_bye for m in round1))
                self.assertTrue(all(m.participant_a is not None and m.participant_b is not None for m in round1))

    def test_bracket_size_and_bye_count_for_non_power_of_two(self):
        cases = {3: (4, 1), 5: (8, 3), 6: (8, 2), 7: (8, 1), 10: (16, 6)}
        for n, (expected_size, expected_byes) in cases.items():
            with self.subTest(n=n):
                bracket = generate_knockout_bracket(list(range(n)))
                self.assertEqual(bracket.bracket_size, expected_size)
                round1_byes = [m for m in bracket.matches if m.round_number == 1 and m.is_bye]
                self.assertEqual(len(round1_byes), expected_byes)

    def test_top_seeds_receive_byes_before_lower_seeds(self):
        # 5 seeded participants (0=seed1 .. 4=seed5) in an 8-bracket: seeds
        # 1-3 should get byes, seeds 4 and 5 must play each other.
        bracket = generate_knockout_bracket(list(range(5)), seeded=True)
        round1 = {m.slot: m for m in bracket.matches if m.round_number == 1}
        bye_winners = {m.bye_winner for m in round1.values() if m.is_bye}
        self.assertEqual(bye_winners, {0, 1, 2})  # seeds 1,2,3 (0-indexed)
        real_matches = [m for m in round1.values() if not m.is_bye]
        self.assertEqual(len(real_matches), 1)
        self.assertEqual({real_matches[0].participant_a, real_matches[0].participant_b}, {3, 4})

    def test_no_participant_faces_themself_or_duplicate(self):
        for n in (3, 4, 5, 8, 10):
            with self.subTest(n=n):
                bracket = generate_knockout_bracket(list(range(n)))
                for m in bracket.matches:
                    if m.participant_a is not None and m.participant_b is not None:
                        self.assertNotEqual(m.participant_a, m.participant_b)

    def test_duplicate_participants_rejected(self):
        with self.assertRaises(ValueError):
            generate_knockout_bracket([1, 2, 2, 3])


class KnockoutBracketPropagationTests(SimpleTestCase):
    def test_five_participants_full_propagation(self):
        # Hand-verified: seeds 1,2,3 (0-indexed 0,1,2) get byes; seeds 4,5
        # (indices 3,4) play a real match. Semifinal pairing per the
        # standard [1,8,4,5,2,7,3,6] seeding: (seed1 vs winner(4v5)) and
        # (seed2 vs seed3) — the latter with BOTH sides already known from
        # byes, but still a real match, never auto-advanced.
        bracket = generate_knockout_bracket(list(range(5)), seeded=True)
        self.assertEqual(bracket.rounds, 3)  # R1, semifinal, final

        round2 = [m for m in bracket.matches if m.round_number == 2]
        self.assertEqual(len(round2), 2)

        # No Round-2+ match is ever flagged as a bye, even when both
        # sides are already known.
        self.assertTrue(all(not m.is_bye for m in round2))

        by_slot = {m.slot: m for m in round2}
        # Match feeding from (seed1-bye, real 4v5 match): one side known.
        one_known = by_slot[0]
        known_sides = [p for p in (one_known.participant_a, one_known.participant_b) if p is not None]
        unknown_sides = [p for p in (one_known.participant_a, one_known.participant_b) if p is None]
        self.assertEqual(known_sides, [0])  # seed 1 (index 0)
        self.assertEqual(len(unknown_sides), 1)

        # Match feeding from two byes (seed2, seed3): both sides known,
        # still a real, playable match.
        both_known = by_slot[1]
        self.assertEqual({both_known.participant_a, both_known.participant_b}, {1, 2})

    def test_final_round_is_fully_undetermined_when_no_byes_feed_it(self):
        bracket = generate_knockout_bracket(list(range(4)))  # no byes at all
        final = [m for m in bracket.matches if m.round_number == bracket.rounds]
        self.assertEqual(len(final), 1)
        self.assertIsNone(final[0].participant_a)
        self.assertIsNone(final[0].participant_b)
        self.assertFalse(final[0].is_bye)

    def test_round_count_matches_log2_bracket_size(self):
        cases = {2: 1, 3: 2, 4: 2, 5: 3, 8: 3, 9: 4, 16: 4}
        for n, expected_rounds in cases.items():
            with self.subTest(n=n):
                bracket = generate_knockout_bracket(list(range(n)))
                self.assertEqual(bracket.rounds, expected_rounds)


class ThirdPlaceMatchTests(SimpleTestCase):
    def test_third_place_added_when_semifinal_exists(self):
        bracket = generate_knockout_bracket(list(range(8)), third_place=True)
        third_place_matches = [m for m in bracket.matches if m.is_third_place]
        self.assertEqual(len(third_place_matches), 1)
        self.assertEqual(third_place_matches[0].round_number, bracket.rounds)
        self.assertTrue(bracket.has_third_place_match)

    def test_no_third_place_without_semifinal(self):
        # n=2 -> 1 round (the final only), no semifinal exists.
        bracket = generate_knockout_bracket([1, 2], third_place=True)
        self.assertEqual(bracket.rounds, 1)
        self.assertFalse(any(m.is_third_place for m in bracket.matches))
        self.assertFalse(bracket.has_third_place_match)

    def test_third_place_off_by_default(self):
        bracket = generate_knockout_bracket(list(range(8)))
        self.assertFalse(any(m.is_third_place for m in bracket.matches))


class UnseededDrawTests(SimpleTestCase):
    def test_random_seed_reproducible(self):
        first = generate_knockout_bracket(list(range(10)), seeded=False, random_seed=7)
        second = generate_knockout_bracket(list(range(10)), seeded=False, random_seed=7)
        self.assertEqual(first, second)

    def test_no_random_seed_preserves_order(self):
        participants = ["d", "b", "a", "c"]
        first = generate_knockout_bracket(participants, seeded=False)
        second = generate_knockout_bracket(participants, seeded=False)
        self.assertEqual(first, second)

    def test_all_participants_appear_exactly_once_across_round_one(self):
        for n in (3, 5, 7, 10):
            with self.subTest(n=n):
                bracket = generate_knockout_bracket(list(range(n)), seeded=False, random_seed=1)
                round1 = [m for m in bracket.matches if m.round_number == 1]
                seen = []
                for m in round1:
                    if m.participant_a is not None:
                        seen.append(m.participant_a)
                    if m.participant_b is not None:
                        seen.append(m.participant_b)
                self.assertEqual(sorted(seen), list(range(n)))


class EdgeCaseTests(SimpleTestCase):
    def test_zero_and_one_participants(self):
        for participants in ([], [1]):
            bracket = generate_knockout_bracket(participants)
            self.assertEqual(bracket.rounds, 0)
            self.assertEqual(bracket.matches, [])

    def test_two_participants_single_final_match(self):
        bracket = generate_knockout_bracket([1, 2])
        self.assertEqual(bracket.rounds, 1)
        self.assertEqual(len(bracket.matches), 1)
        self.assertFalse(bracket.matches[0].is_bye)
