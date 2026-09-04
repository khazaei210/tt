from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.models import Match, MatchStatus
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    StaffRole,
    Tournament,
    TournamentStaff,
    TournamentStatus,
)
from apps.tournaments.services.dashboard import build_manager_dashboard

User = get_user_model()


class ManagerDashboardServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager", password="pw")
        self.referee = User.objects.create_user(username="referee", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.superuser = User.objects.create_superuser(username="admin", password="pw", email="a@example.com")

        self.managed = Tournament.objects.create(name="Managed Open", status=TournamentStatus.ONGOING)
        self.other = Tournament.objects.create(name="Other Open", status=TournamentStatus.ONGOING)
        TournamentStaff.objects.create(tournament=self.managed, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER)
        TournamentStaff.objects.create(tournament=self.managed, user=self.referee, role=StaffRole.REFEREE)

        self.competition = Competition.objects.create(
            tournament=self.managed, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Round 1", stage_format=StageFormat.KNOCKOUT
        )
        self.players = [
            Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M"),
            )
            for i in range(4)
        ]
        self.live_match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.players[0],
            participant_b=self.players[1],
            status=MatchStatus.LIVE,
        )
        self.upcoming_match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.players[2],
            participant_b=self.players[3],
            status=MatchStatus.SCHEDULED,
        )
        self.completed_match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=2,
            participant_a=self.players[0],
            participant_b=self.players[2],
            status=MatchStatus.COMPLETED,
            winner=self.players[0],
        )

    def test_manager_only_sees_their_own_tournament(self):
        dashboard = build_manager_dashboard(self.manager)
        tournament_ids = {row.tournament.pk for row in dashboard.tournaments}
        self.assertEqual(tournament_ids, {self.managed.pk})

    def test_referee_role_alone_does_not_grant_dashboard_visibility(self):
        # Referee/Scorekeeper get their own dashboard elsewhere (section 21);
        # this one is scoped to management roles (Admin/Manager) only.
        dashboard = build_manager_dashboard(self.referee)
        self.assertEqual(dashboard.tournaments, [])

    def test_user_with_no_role_sees_empty_dashboard(self):
        dashboard = build_manager_dashboard(self.outsider)
        self.assertEqual(dashboard.tournaments, [])
        self.assertEqual(dashboard.live_matches, [])
        self.assertEqual(dashboard.total_participants, 0)

    def test_superuser_sees_every_tournament(self):
        dashboard = build_manager_dashboard(self.superuser)
        tournament_ids = {row.tournament.pk for row in dashboard.tournaments}
        self.assertEqual(tournament_ids, {self.managed.pk, self.other.pk})

    def test_matches_are_bucketed_by_status(self):
        dashboard = build_manager_dashboard(self.manager)
        self.assertEqual([m.pk for m in dashboard.live_matches], [self.live_match.pk])
        self.assertEqual([m.pk for m in dashboard.upcoming_matches], [self.upcoming_match.pk])
        self.assertEqual([m.pk for m in dashboard.recent_completed_matches], [self.completed_match.pk])

    def test_matches_from_other_tournaments_are_excluded(self):
        other_competition = Competition.objects.create(
            tournament=self.other, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        other_stage = Stage.objects.create(
            competition=other_competition, name="Round 1", stage_format=StageFormat.KNOCKOUT
        )
        Match.objects.create(
            competition=other_competition, stage=other_stage, round_number=1, status=MatchStatus.LIVE
        )
        dashboard = build_manager_dashboard(self.manager)
        self.assertEqual([m.pk for m in dashboard.live_matches], [self.live_match.pk])

    def test_tournament_progress_counts_and_percentage(self):
        dashboard = build_manager_dashboard(self.manager)
        row = dashboard.tournaments[0]
        self.assertEqual(row.competition_count, 1)
        self.assertEqual(row.participant_count, 4)
        self.assertEqual(row.total_matches, 3)
        self.assertEqual(row.completed_matches, 1)
        self.assertEqual(row.progress_percent, 33)

    def test_bye_participants_excluded_from_participant_count(self):
        Participant.objects.create(competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, is_bye=True)
        dashboard = build_manager_dashboard(self.manager)
        row = dashboard.tournaments[0]
        self.assertEqual(row.participant_count, 4)

    def test_tournament_with_no_matches_has_zero_percent_progress(self):
        Tournament.objects.filter(pk=self.managed.pk)  # sanity: fixture exists
        empty_tournament = Tournament.objects.create(name="Fresh Open", status=TournamentStatus.DRAFT)
        TournamentStaff.objects.create(
            tournament=empty_tournament, user=self.manager, role=StaffRole.TOURNAMENT_ADMIN
        )
        dashboard = build_manager_dashboard(self.manager)
        row = next(r for r in dashboard.tournaments if r.tournament.pk == empty_tournament.pk)
        self.assertEqual(row.total_matches, 0)
        self.assertEqual(row.progress_percent, 0)


class ManagerDashboardViewTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager", password="pw")
        self.tournament = Tournament.objects.create(name="Managed Open")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER
        )

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("tournaments:manager_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_manager_sees_their_tournament(self):
        self.client.login(username="manager", password="pw")
        response = self.client.get(reverse("tournaments:manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Managed Open")

    def test_authenticated_user_with_no_role_gets_empty_state(self):
        User.objects.create_user(username="outsider", password="pw")
        self.client.login(username="outsider", password="pw")
        response = self.client.get(reverse("tournaments:manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Managed Open")
