from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.tournaments.models import Competition, ParticipantType, Tournament


class ReportViewTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        Competition.objects.create(tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL)
        self.player = Player.objects.create(first_name="View", last_name="Test", gender="M")

    def test_tournament_report_is_public(self):
        response = self.client.get(reverse("reports:tournament_report", args=[self.tournament.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Singles")

    def test_player_statistics_is_public(self):
        response = self.client.get(reverse("reports:player_statistics", args=[self.player.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Test")

    def test_unknown_tournament_404s(self):
        response = self.client.get(reverse("reports:tournament_report", args=[999999]))
        self.assertEqual(response.status_code, 404)
