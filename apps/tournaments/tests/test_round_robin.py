from itertools import combinations

from django.test import SimpleTestCase

from apps.tournaments.services.round_robin import generate_round_robin


def all_unordered_pairs(schedule):
    return [frozenset((f.participant_a, f.participant_b)) for f in schedule.fixtures]


class SingleRoundRobinTests(SimpleTestCase):
    def assertEveryPairMeetsExactlyOnce(self, n):
        participants = list(range(n))
        schedule = generate_round_robin(participants, legs=1)
        pairs = all_unordered_pairs(schedule)

        expected_pairs = {frozenset(pair) for pair in combinations(participants, 2)}
        self.assertEqual(set(pairs), expected_pairs)
        # No duplicates: each pair appears exactly once.
        self.assertEqual(len(pairs), len(expected_pairs))
        self.assertEqual(len(pairs), n * (n - 1) // 2)

    def assertEveryParticipantPlaysEveryOther(self, n):
        participants = list(range(n))
        schedule = generate_round_robin(participants, legs=1)
        opponents = {p: set() for p in participants}
        for f in schedule.fixtures:
            opponents[f.participant_a].add(f.participant_b)
            opponents[f.participant_b].add(f.participant_a)
        for p in participants:
            self.assertEqual(opponents[p], set(participants) - {p}, f"participant {p} did not play everyone")

    def test_even_counts_no_byes(self):
        for n in (4, 8, 10, 16):
            with self.subTest(n=n):
                schedule = generate_round_robin(list(range(n)), legs=1)
                self.assertEqual(schedule.byes, {})
                self.assertEqual(schedule.rounds, n - 1)
                self.assertEveryPairMeetsExactlyOnce(n)
                self.assertEveryParticipantPlaysEveryOther(n)

    def test_odd_counts_have_exactly_one_bye_per_round_and_per_participant(self):
        for n in (3, 5):
            with self.subTest(n=n):
                participants = list(range(n))
                schedule = generate_round_robin(participants, legs=1)
                self.assertEqual(schedule.rounds, n)
                # Exactly one bye recorded per round.
                self.assertEqual(set(schedule.byes.keys()), set(range(1, n + 1)))
                # Each participant sits out exactly one round.
                bye_counts = {p: 0 for p in participants}
                for p in schedule.byes.values():
                    bye_counts[p] += 1
                self.assertEqual(set(bye_counts.values()), {1})
                self.assertEveryPairMeetsExactlyOnce(n)
                self.assertEveryParticipantPlaysEveryOther(n)

    def test_bye_participant_plays_no_match_that_round(self):
        schedule = generate_round_robin(list(range(5)), legs=1)
        for round_number, bye_participant in schedule.byes.items():
            round_fixtures = [f for f in schedule.fixtures if f.round_number == round_number]
            round_players = {p for f in round_fixtures for p in (f.participant_a, f.participant_b)}
            self.assertNotIn(bye_participant, round_players)

    def test_matches_per_round_odd_count(self):
        # n=5 -> 2 real matches per round (one participant byes each round).
        schedule = generate_round_robin(list(range(5)), legs=1)
        for round_number in range(1, schedule.rounds + 1):
            count = sum(1 for f in schedule.fixtures if f.round_number == round_number)
            self.assertEqual(count, 2)

    def test_matches_per_round_even_count(self):
        # n=8 -> 4 matches per round.
        schedule = generate_round_robin(list(range(8)), legs=1)
        for round_number in range(1, schedule.rounds + 1):
            count = sum(1 for f in schedule.fixtures if f.round_number == round_number)
            self.assertEqual(count, 4)

    def test_no_participant_plays_twice_in_the_same_round(self):
        for n in (3, 4, 5, 8, 10, 16):
            with self.subTest(n=n):
                schedule = generate_round_robin(list(range(n)), legs=1)
                for round_number in range(1, schedule.rounds + 1):
                    round_fixtures = [f for f in schedule.fixtures if f.round_number == round_number]
                    players = [p for f in round_fixtures for p in (f.participant_a, f.participant_b)]
                    self.assertEqual(len(players), len(set(players)))


class DoubleRoundRobinTests(SimpleTestCase):
    def test_every_pair_meets_exactly_twice_once_each_direction(self):
        for n in (4, 5):
            with self.subTest(n=n):
                participants = list(range(n))
                schedule = generate_round_robin(participants, legs=2)
                ordered_pairs = [(f.participant_a, f.participant_b) for f in schedule.fixtures]

                for a, b in combinations(participants, 2):
                    self.assertEqual(ordered_pairs.count((a, b)), 1)
                    self.assertEqual(ordered_pairs.count((b, a)), 1)

    def test_round_count_and_total_matches_double(self):
        single = generate_round_robin(list(range(6)), legs=1)
        double = generate_round_robin(list(range(6)), legs=2)
        self.assertEqual(double.rounds, single.rounds * 2)
        self.assertEqual(len(double.fixtures), len(single.fixtures) * 2)

    def test_second_leg_byes_offset_correctly(self):
        schedule = generate_round_robin(list(range(5)), legs=2)
        single_leg_rounds = 5
        # Round r and round r + single_leg_rounds should have the same bye participant.
        for round_number in range(1, single_leg_rounds + 1):
            self.assertEqual(
                schedule.byes[round_number],
                schedule.byes[round_number + single_leg_rounds],
            )


class DeterminismTests(SimpleTestCase):
    def test_no_seed_preserves_input_order_deterministically(self):
        participants = ["d", "b", "a", "c"]
        first = generate_round_robin(participants, legs=1)
        second = generate_round_robin(participants, legs=1)
        self.assertEqual(first, second)

    def test_same_seed_reproduces_identical_schedule(self):
        participants = list(range(10))
        first = generate_round_robin(participants, seed=42)
        second = generate_round_robin(participants, seed=42)
        self.assertEqual(first, second)

    def test_different_seeds_can_produce_different_schedules(self):
        participants = list(range(10))
        first = generate_round_robin(participants, seed=1)
        second = generate_round_robin(participants, seed=2)
        self.assertNotEqual(first.fixtures, second.fixtures)
        # Regardless of order, the underlying pairing set is unaffected.
        self.assertEqual(set(all_unordered_pairs(first)), set(all_unordered_pairs(second)))


class EdgeCaseTests(SimpleTestCase):
    def test_zero_participants(self):
        schedule = generate_round_robin([])
        self.assertEqual(schedule.rounds, 0)
        self.assertEqual(schedule.fixtures, [])

    def test_one_participant(self):
        schedule = generate_round_robin([1])
        self.assertEqual(schedule.rounds, 0)
        self.assertEqual(schedule.fixtures, [])

    def test_two_participants(self):
        schedule = generate_round_robin([1, 2])
        self.assertEqual(schedule.rounds, 1)
        self.assertEqual(len(schedule.fixtures), 1)
        self.assertEqual(schedule.byes, {})

    def test_duplicate_participants_rejected(self):
        with self.assertRaises(ValueError):
            generate_round_robin([1, 2, 2, 3])

    def test_legs_below_one_rejected(self):
        with self.assertRaises(ValueError):
            generate_round_robin([1, 2, 3], legs=0)
