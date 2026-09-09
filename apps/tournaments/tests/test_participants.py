from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import DoublesPair, Player
from apps.teams.models import Team
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


class DisplayNameStaysInSyncTests(TestCase):
    """Participant.display_name is a denormalized cache of the underlying
    Player/DoublesPair/Team's name (kept for query/ordering performance —
    see Participant.refresh_display_name) — renaming the source must push
    the new name out to every Participant row derived from it, not just
    apply at the moment a Participant is first created."""

    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")

    def test_renaming_a_player_updates_their_individual_participant(self):
        competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        player = Player.objects.create(first_name="Old", last_name="Name", gender="M", mobile_number="09000001111")
        participant = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
        )
        self.assertEqual(participant.display_name, "Old Name")

        player.first_name = "New"
        player.save()

        participant.refresh_from_db()
        self.assertEqual(participant.display_name, "New Name")

    def test_renaming_a_player_updates_their_doubles_participant(self):
        competition = Competition.objects.create(
            tournament=self.tournament, name="Doubles", participant_type=ParticipantType.DOUBLES
        )
        player_one = Player.objects.create(first_name="A", last_name="One", gender="M", mobile_number="09000002222")
        player_two = Player.objects.create(first_name="B", last_name="Two", gender="M", mobile_number="09000003333")
        pair = DoublesPair.objects.create(player_one=player_one, player_two=player_two)
        participant = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair
        )
        self.assertEqual(participant.display_name, "A One / B Two")

        player_one.first_name = "Renamed"
        player_one.save()

        participant.refresh_from_db()
        self.assertEqual(participant.display_name, "Renamed One / B Two")

    def test_renaming_a_team_updates_their_team_participant(self):
        competition = Competition.objects.create(
            tournament=self.tournament, name="Team Event", participant_type=ParticipantType.TEAM
        )
        team = Team.objects.create(name="Old Team Name")
        participant = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.TEAM, team=team
        )
        self.assertEqual(participant.display_name, "Old Team Name")

        team.name = "New Team Name"
        team.save()

        participant.refresh_from_db()
        self.assertEqual(participant.display_name, "New Team Name")

    def test_bye_participants_are_never_touched_by_a_rename(self):
        competition = Competition.objects.create(
            tournament=self.tournament, name="Singles 2", participant_type=ParticipantType.INDIVIDUAL
        )
        player = Player.objects.create(first_name="Old", last_name="Name", gender="M", mobile_number="09000004444")
        bye = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.INDIVIDUAL, is_bye=True
        )
        original_display_name = bye.display_name
        player.first_name = "New"
        player.save()
        bye.refresh_from_db()
        self.assertEqual(bye.display_name, original_display_name)
