from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Participant,
    ParticipantType,
    StaffRole,
    Tournament,
    TournamentStaff,
)

User = get_user_model()


class BulkParticipantAddTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER
        )
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")
        self.players = [
            Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900000{i:04d}")
            for i in range(4)
        ]

    def test_adds_every_selected_player_in_one_request(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk}),
            {"selected": [p.pk for p in self.players[:3]]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.competition.participants.count(), 3)

    def test_display_name_is_populated_for_bulk_added_participants(self):
        # Participant.save() derives display_name from the linked player —
        # this must still happen for bulk-added rows, not just single adds.
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk}),
            {"selected": [self.players[0].pk]},
        )
        participant = Participant.objects.get(competition=self.competition, individual_player=self.players[0])
        self.assertEqual(participant.display_name, self.players[0].full_name)

    def test_already_added_players_are_not_offered_again(self):
        Participant.objects.create(
            competition=self.competition,
            participant_type=ParticipantType.INDIVIDUAL,
            individual_player=self.players[0],
        )
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk}),
            {"selected": [self.players[0].pk]},
        )
        self.assertEqual(response.status_code, 200)
        # Rejected as an invalid choice — no duplicate participant created.
        self.assertEqual(self.competition.participants.count(), 1)

    def test_requires_management_role(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk}),
            {"selected": [self.players[0].pk]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.competition.participants.count(), 0)

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk}),
            {"selected": [self.players[0].pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_get_not_allowed(self):
        self.client.login(username="manager", password="pw")
        response = self.client.get(
            reverse("tournaments:participant_bulk_add", kwargs={"competition_pk": self.competition.pk})
        )
        self.assertEqual(response.status_code, 405)
