from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import (
    MatchAlreadyStartedError,
    NotEnoughParticipantsError,
    ParticipantNotInBracketError,
    ScheduleAlreadyGeneratedError,
    clear_stage_bracket,
    generate_stage_bracket,
    start_match,
    swap_bracket_participants,
)
from apps.players.models import Player
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament
from apps.tournaments.services.setup import StageLockedError


class StageBracketServiceTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT)

    def _add_participants(self, count, seeded=False):
        participants = []
        for i in range(count):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900009{i:04d}")
            participant = Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=player,
                seed=(i + 1) if seeded else None,
            )
            participants.append(participant)
        return participants

    def test_power_of_two_bracket_has_no_byes(self):
        self._add_participants(4, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        matches = Match.objects.filter(stage=self.stage)
        self.assertEqual(matches.count(), 3)  # 2 R1 + 1 final
        self.assertFalse(matches.filter(is_bye=True).exists())
        round1 = matches.filter(round_number=1)
        self.assertEqual(round1.count(), 2)
        for m in round1:
            self.assertIsNotNone(m.participant_a_id)
            self.assertIsNotNone(m.participant_b_id)

    def test_non_power_of_two_creates_bye_participant_and_matches(self):
        self._add_participants(5, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        matches = Match.objects.filter(stage=self.stage)
        # bracket_size=8 -> 4 R1 + 2 R2 + 1 final = 7 matches
        self.assertEqual(matches.count(), 7)

        bye_matches = matches.filter(is_bye=True)
        self.assertEqual(bye_matches.count(), 3)
        for m in bye_matches:
            self.assertTrue(m.participant_a.is_bye or m.participant_b.is_bye)

        # Exactly one BYE participant row was created and reused across all bye matches.
        bye_participant = Participant.objects.get(competition=self.competition, is_bye=True)
        for m in bye_matches:
            self.assertIn(bye_participant.id, (m.participant_a_id, m.participant_b_id))

    def test_final_round_pending_when_no_bye_feeds_it(self):
        self._add_participants(4, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        final = Match.objects.get(stage=self.stage, round_number=2)
        self.assertIsNone(final.participant_a_id)
        self.assertIsNone(final.participant_b_id)
        self.assertFalse(final.is_bye)

    def test_semifinal_with_two_byes_has_both_participants_known(self):
        # 5 seeded participants -> seeds 2 and 3 both get byes and meet
        # each other in the semifinal with both sides already known.
        self._add_participants(5, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        semifinal_matches = Match.objects.filter(stage=self.stage, round_number=2)
        both_known = [m for m in semifinal_matches if m.participant_a_id and m.participant_b_id]
        self.assertEqual(len(both_known), 1)
        self.assertFalse(both_known[0].is_bye)

    def test_third_place_match_created_when_requested(self):
        self._add_participants(8, seeded=True)
        generate_stage_bracket(self.stage, seeded=True, third_place=True)
        self.assertTrue(Match.objects.filter(stage=self.stage, is_third_place=True).exists())

    def test_raises_if_bracket_already_generated(self):
        self._add_participants(4, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        with self.assertRaises(ScheduleAlreadyGeneratedError):
            generate_stage_bracket(self.stage, seeded=True)
        self.assertEqual(Match.objects.filter(stage=self.stage).count(), 3)

    def test_raises_if_fewer_than_two_participants(self):
        self._add_participants(1)
        with self.assertRaises(NotEnoughParticipantsError):
            generate_stage_bracket(self.stage)
        self.assertEqual(Match.objects.filter(stage=self.stage).count(), 0)

    def test_clear_bracket_allows_regeneration(self):
        self._add_participants(4, seeded=True)
        generate_stage_bracket(self.stage, seeded=True)
        clear_stage_bracket(self.stage)
        self.assertEqual(Match.objects.filter(stage=self.stage).count(), 0)
        generate_stage_bracket(self.stage, seeded=True)
        self.assertEqual(Match.objects.filter(stage=self.stage).count(), 3)

    def test_unseeded_draw_uses_random_seed_deterministically(self):
        self._add_participants(4, seeded=False)
        generate_stage_bracket(self.stage, seeded=False, random_seed=99)
        first_pairs = set(
            Match.objects.filter(stage=self.stage, round_number=1).values_list(
                "participant_a_id", "participant_b_id"
            )
        )
        clear_stage_bracket(self.stage)
        generate_stage_bracket(self.stage, seeded=False, random_seed=99)
        second_pairs = set(
            Match.objects.filter(stage=self.stage, round_number=1).values_list(
                "participant_a_id", "participant_b_id"
            )
        )
        self.assertEqual(first_pairs, second_pairs)


class SwapBracketParticipantsTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT)
        self.participants = []
        for i in range(4):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900010{i:04d}")
            self.participants.append(
                Participant.objects.create(
                    competition=self.competition,
                    participant_type=ParticipantType.INDIVIDUAL,
                    individual_player=player,
                    seed=i + 1,
                )
            )
        generate_stage_bracket(self.stage, seeded=True)
        self.round_one = list(self.stage.matches.filter(round_number=1).order_by("bracket_slot"))

    def test_swaps_the_two_participants_slots(self):
        match_a, match_b = self.round_one
        a_id, b_id = match_a.participant_a_id, match_b.participant_a_id
        swap_bracket_participants(self.stage, a_id, b_id)
        match_a.refresh_from_db()
        match_b.refresh_from_db()
        self.assertEqual(match_a.participant_a_id, b_id)
        self.assertEqual(match_b.participant_a_id, a_id)

    def test_rejects_the_same_participant_twice(self):
        a_id = self.round_one[0].participant_a_id
        with self.assertRaises(ParticipantNotInBracketError):
            swap_bracket_participants(self.stage, a_id, a_id)

    def test_rejects_two_participants_already_in_the_same_match(self):
        match = self.round_one[0]
        with self.assertRaises(ParticipantNotInBracketError):
            swap_bracket_participants(self.stage, match.participant_a_id, match.participant_b_id)

    def test_rejects_a_participant_not_in_the_bracket(self):
        outsider = Participant.objects.create(
            competition=self.competition,
            participant_type=ParticipantType.INDIVIDUAL,
            individual_player=Player.objects.create(
                first_name="Out", last_name="Sider", gender="M", mobile_number="09000109999"
            ),
        )
        a_id = self.round_one[0].participant_a_id
        with self.assertRaises(ParticipantNotInBracketError):
            swap_bracket_participants(self.stage, a_id, outsider.id)

    def test_rejects_once_a_match_has_started(self):
        match_a, match_b = self.round_one
        start_match(match_a)
        with self.assertRaises(MatchAlreadyStartedError):
            swap_bracket_participants(self.stage, match_a.participant_a_id, match_b.participant_a_id)

    def test_rejects_when_stage_is_locked(self):
        match_a, match_b = self.round_one
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        with self.assertRaises(StageLockedError):
            swap_bracket_participants(self.stage, match_a.participant_a_id, match_b.participant_a_id)
