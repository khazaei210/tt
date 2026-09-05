from django.test import TestCase
from django.urls import reverse

from apps.matches.services import generate_group_schedule, record_set_score
from apps.players.models import Player
from apps.tournaments.models import Competition, Group, GroupParticipant, Participant, ParticipantType, Stage, StageFormat, Tournament


class GroupStandingsCsvTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.group = Group.objects.create(stage=self.stage, name="A")
        self.player_a = Player.objects.create(first_name="Csv", last_name="A", gender="M")
        self.player_b = Player.objects.create(first_name="Csv", last_name="B", gender="M")
        for player in (self.player_a, self.player_b):
            participant = Participant.objects.create(
                competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
            )
            GroupParticipant.objects.create(group=self.group, participant=participant)
        generate_group_schedule(self.group)
        match = self.group.matches.first()
        record_set_score(match, 1, 11, 5)
        record_set_score(match, 2, 11, 5)
        record_set_score(match, 3, 11, 5)

    def test_standings_csv_is_public_and_contains_participant_names(self):
        response = self.client.get(reverse("tournaments:group_standings_csv", args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8-sig")
        self.assertIn("Csv A", content)
        self.assertIn("Csv B", content)
