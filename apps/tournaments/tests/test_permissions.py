from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.models import Match
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Group,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    StaffRole,
    Tournament,
    TournamentStaff,
)

User = get_user_model()


class TournamentPermissionTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Existing Open")
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")
        self.superuser = User.objects.create_superuser(username="admin", password="pw", email="a@example.com")
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER
        )


class TournamentCreationPermissionTests(TournamentPermissionTestCase):
    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(reverse("tournaments:add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_non_staff_user_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("tournaments:add"))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_create_and_becomes_admin(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(
            reverse("tournaments:add"),
            {"name": "New Open", "status": "draft"},
        )
        self.assertEqual(response.status_code, 302)
        tournament = Tournament.objects.get(name="New Open")
        self.assertTrue(
            TournamentStaff.objects.filter(
                tournament=tournament, user=self.staff_user, role=StaffRole.TOURNAMENT_ADMIN
            ).exists()
        )

    def test_superuser_can_create_without_being_staff_flagged(self):
        self.client.login(username="admin", password="pw")
        response = self.client.get(reverse("tournaments:add"))
        self.assertEqual(response.status_code, 200)


class TournamentEditPermissionTests(TournamentPermissionTestCase):
    def test_anonymous_redirected_to_login_on_edit(self):
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_user_without_role_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 403)

    def test_staff_flag_alone_is_not_enough_without_a_tournament_role(self):
        # Being globally "staff" grants registry (players/teams) access,
        # but NOT tournament management — that requires an explicit
        # TournamentStaff role (or superuser).
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 403)

    def test_manager_role_on_this_tournament_can_edit(self):
        self.client.login(username="manager", password="pw")
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 200)

    def test_manager_role_does_not_grant_access_to_other_tournaments(self):
        other_tournament = Tournament.objects.create(name="Other Open")
        self.client.login(username="manager", password="pw")
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": other_tournament.pk}))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_edit_any_tournament(self):
        self.client.login(username="admin", password="pw")
        response = self.client.get(reverse("tournaments:edit", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 200)

    def test_delete_requires_management_role(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("tournaments:delete", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Tournament.objects.filter(pk=self.tournament.pk).exists())


class PublicReadAccessTests(TournamentPermissionTestCase):
    """Read views must stay public — only mutations require authorization."""

    def test_anonymous_can_view_tournament_list(self):
        response = self.client.get(reverse("tournaments:list"))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_can_view_tournament_detail(self):
        response = self.client.get(reverse("tournaments:detail", kwargs={"pk": self.tournament.pk}))
        self.assertEqual(response.status_code, 200)


class NestedResourcePermissionTests(TournamentPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.group = Group.objects.create(stage=self.stage, name="Group A")

    def test_competition_add_requires_management_role_on_parent_tournament(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(
            reverse("tournaments:competition_add", kwargs={"tournament_pk": self.tournament.pk})
        )
        self.assertEqual(response.status_code, 403)

        self.client.login(username="manager", password="pw")
        response = self.client.get(
            reverse("tournaments:competition_add", kwargs={"tournament_pk": self.tournament.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_stage_delete_requires_role_derived_through_competition(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("tournaments:stage_delete", kwargs={"pk": self.stage.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Stage.objects.filter(pk=self.stage.pk).exists())

        self.client.login(username="manager", password="pw")
        response = self.client.post(reverse("tournaments:stage_delete", kwargs={"pk": self.stage.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Stage.objects.filter(pk=self.stage.pk).exists())

    def test_group_delete_requires_role_derived_through_stage_and_competition(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("tournaments:group_delete", kwargs={"pk": self.group.pk}))
        self.assertEqual(response.status_code, 403)

        self.client.login(username="manager", password="pw")
        response = self.client.post(reverse("tournaments:group_delete", kwargs={"pk": self.group.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())


class MatchScoringPermissionTests(TournamentPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.group = Group.objects.create(stage=self.stage, name="Group A")
        p1 = Player.objects.create(first_name="A", last_name="Test", gender="M")
        p2 = Player.objects.create(first_name="B", last_name="Test", gender="M")
        self.participant_a = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=p1
        )
        self.participant_b = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=p2
        )
        self.match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            group=self.group,
            round_number=1,
            participant_a=self.participant_a,
            participant_b=self.participant_b,
        )
        self.referee = User.objects.create_user(username="ref", password="pw")
        TournamentStaff.objects.create(tournament=self.tournament, user=self.referee, role=StaffRole.REFEREE)

    def test_anonymous_cannot_enter_score(self):
        response = self.client.post(
            reverse("matches:set_save", kwargs={"pk": self.match.pk}),
            {"set_number": 1, "participant_a_score": 11, "participant_b_score": 5},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        self.assertEqual(self.match.sets.count(), 0)

    def test_plain_authenticated_user_cannot_enter_score(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(
            reverse("matches:set_save", kwargs={"pk": self.match.pk}),
            {"set_number": 1, "participant_a_score": 11, "participant_b_score": 5},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.match.sets.count(), 0)

    def test_referee_can_enter_score(self):
        self.client.login(username="ref", password="pw")
        response = self.client.post(
            reverse("matches:set_save", kwargs={"pk": self.match.pk}),
            {"set_number": 1, "participant_a_score": 11, "participant_b_score": 5},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.match.sets.count(), 1)

    def test_tournament_manager_can_also_enter_score(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("matches:set_save", kwargs={"pk": self.match.pk}),
            {"set_number": 1, "participant_a_score": 11, "participant_b_score": 5},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.match.sets.count(), 1)

    def test_match_detail_page_is_publicly_viewable(self):
        response = self.client.get(reverse("matches:detail", kwargs={"pk": self.match.pk}))
        self.assertEqual(response.status_code, 200)
