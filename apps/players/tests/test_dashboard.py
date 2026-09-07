from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.models import Match, MatchStatus
from apps.players.dashboard import build_player_dashboard
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
    TournamentStatus,
)

User = get_user_model()


class PlayerDashboardViewTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("players:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_without_player_profile_shows_empty_state(self):
        User.objects.create_user(username="plainuser", password="pw")
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("players:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "isn't linked to a player profile")

    def test_authenticated_player_sees_dashboard(self):
        user = User.objects.create_user(username="playeruser", password="pw")
        Player.objects.create(first_name="A", last_name="Test", gender="M", user=user)
        self.client.login(username="playeruser", password="pw")
        response = self.client.get(reverse("players:dashboard"))
        self.assertEqual(response.status_code, 200)


class BuildPlayerDashboardServiceTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(first_name="A", last_name="Test", gender="M")
        self.opponent = Player.objects.create(first_name="B", last_name="Rival", gender="M")
        self.tournament = Tournament.objects.create(name="Open Cup", status=TournamentStatus.ONGOING)
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Round 1", stage_format=StageFormat.KNOCKOUT
        )
        self.participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player
        )
        self.opponent_participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.opponent
        )

    def test_none_player_returns_empty_dashboard(self):
        dashboard = build_player_dashboard(None)
        self.assertEqual(dashboard.upcoming_matches, [])
        self.assertEqual(dashboard.tournaments, [])

    def test_player_with_no_participation_returns_empty_dashboard(self):
        lone_player = Player.objects.create(first_name="C", last_name="Solo", gender="F")
        dashboard = build_player_dashboard(lone_player)
        self.assertEqual(dashboard.upcoming_matches, [])
        self.assertEqual(dashboard.tournaments, [])

    def test_scheduled_match_appears_in_upcoming(self):
        match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.participant,
            participant_b=self.opponent_participant,
            status=MatchStatus.SCHEDULED,
        )
        dashboard = build_player_dashboard(self.player)
        self.assertEqual(dashboard.upcoming_matches, [match])
        self.assertEqual(dashboard.tournaments, [self.tournament])

    def test_completed_match_is_excluded_from_upcoming(self):
        Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.participant,
            participant_b=self.opponent_participant,
            status=MatchStatus.COMPLETED,
            winner=self.participant,
        )
        dashboard = build_player_dashboard(self.player)
        self.assertEqual(dashboard.upcoming_matches, [])
        self.assertEqual(dashboard.tournaments, [self.tournament])
