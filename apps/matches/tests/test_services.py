from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import (
    NotEnoughParticipantsError,
    ScheduleAlreadyGeneratedError,
    clear_group_schedule,
    generate_group_schedule,
)
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
)


class GroupScheduleServiceTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.group = Group.objects.create(stage=self.stage, name="Group A")

    def _add_participants(self, count):
        participants = []
        for i in range(count):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M")
            participant = Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=player,
            )
            GroupParticipant.objects.create(group=self.group, participant=participant)
            participants.append(participant)
        return participants

    def test_generates_correct_number_of_matches_for_even_group(self):
        self._add_participants(4)
        generate_group_schedule(self.group)
        # 4 participants, single leg -> 4*3/2 = 6 matches over 3 rounds.
        self.assertEqual(Match.objects.filter(group=self.group).count(), 6)
        self.assertEqual(
            set(Match.objects.filter(group=self.group).values_list("round_number", flat=True)),
            {1, 2, 3},
        )

    def test_generates_correct_number_of_matches_for_odd_group(self):
        self._add_participants(5)
        generate_group_schedule(self.group)
        # 5 participants -> 5*4/2 = 10 matches over 5 rounds.
        self.assertEqual(Match.objects.filter(group=self.group).count(), 10)

    def test_matches_are_scoped_to_competition_and_stage(self):
        self._add_participants(3)
        generate_group_schedule(self.group)
        for match in Match.objects.filter(group=self.group):
            self.assertEqual(match.competition_id, self.competition.pk)
            self.assertEqual(match.stage_id, self.stage.pk)

    def test_double_round_robin_doubles_matches(self):
        self._add_participants(4)
        generate_group_schedule(self.group, legs=2)
        self.assertEqual(Match.objects.filter(group=self.group).count(), 12)

    def test_raises_if_schedule_already_generated(self):
        self._add_participants(4)
        generate_group_schedule(self.group)
        with self.assertRaises(ScheduleAlreadyGeneratedError):
            generate_group_schedule(self.group)
        # No extra matches created by the failed second call.
        self.assertEqual(Match.objects.filter(group=self.group).count(), 6)

    def test_raises_if_fewer_than_two_participants(self):
        self._add_participants(1)
        with self.assertRaises(NotEnoughParticipantsError):
            generate_group_schedule(self.group)
        self.assertEqual(Match.objects.filter(group=self.group).count(), 0)

    def test_clear_schedule_removes_matches_and_allows_regeneration(self):
        self._add_participants(4)
        generate_group_schedule(self.group)
        clear_group_schedule(self.group)
        self.assertEqual(Match.objects.filter(group=self.group).count(), 0)
        # Regenerating after clearing should work without error.
        generate_group_schedule(self.group)
        self.assertEqual(Match.objects.filter(group=self.group).count(), 6)

    def test_no_participant_faces_themselves(self):
        self._add_participants(5)
        generate_group_schedule(self.group)
        for match in Match.objects.filter(group=self.group):
            self.assertNotEqual(match.participant_a_id, match.participant_b_id)
