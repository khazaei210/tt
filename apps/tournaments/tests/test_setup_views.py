from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.rankings.models import EloRating
from apps.tournaments.models import (
    Competition,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    StaffRole,
    Stage,
    StageFormat,
    Tournament,
    TournamentStaff,
)

User = get_user_model()


def make_player(i):
    return Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900001{i:04d}")


class SetupViewTestCase(TestCase):
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
        self.participants = [
            Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=make_player(i),
                seed=i + 1,
            )
            for i in range(4)
        ]


class CompetitionSeedByRatingViewTests(SetupViewTestCase):
    def test_requires_management_role(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(
            reverse("tournaments:competition_seed_by_rating", kwargs={"competition_pk": self.competition.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_can_reseed_by_rating(self):
        EloRating.objects.create(
            player=self.participants[0].individual_player, category=self.competition.ranking_category, rating=2000
        )
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:competition_seed_by_rating", kwargs={"competition_pk": self.competition.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.participants[0].refresh_from_db()
        self.assertEqual(self.participants[0].seed, 1)


class StageAutoAssignGroupsViewTests(SetupViewTestCase):
    def setUp(self):
        super().setUp()
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )

    def test_requires_management_role(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("tournaments:stage_auto_assign_groups", kwargs={"pk": self.stage.pk}))
        self.assertEqual(response.status_code, 403)

    def test_manager_gets_a_friendly_error_with_no_groups(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:stage_auto_assign_groups", kwargs={"pk": self.stage.pk}), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GroupParticipant.objects.count(), 0)

    def test_manager_can_auto_assign_into_existing_groups(self):
        Group.objects.create(stage=self.stage, name="A", order=1)
        Group.objects.create(stage=self.stage, name="B", order=2)
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:stage_auto_assign_groups", kwargs={"pk": self.stage.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GroupParticipant.objects.filter(group__stage=self.stage).count(), 4)


class StageGenerateAllSchedulesViewTests(SetupViewTestCase):
    def setUp(self):
        super().setUp()
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.group_a = Group.objects.create(stage=self.stage, name="A", order=1)
        self.group_b = Group.objects.create(stage=self.stage, name="B", order=2)
        for p in self.participants[:2]:
            GroupParticipant.objects.create(group=self.group_a, participant=p)
        for p in self.participants[2:]:
            GroupParticipant.objects.create(group=self.group_b, participant=p)

    def test_requires_management_role(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(
            reverse("tournaments:stage_generate_all_schedules", kwargs={"pk": self.stage.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_generates_matches_for_every_group_in_one_request(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:stage_generate_all_schedules", kwargs={"pk": self.stage.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.group_a.matches.exists())
        self.assertTrue(self.group_b.matches.exists())

    def test_second_call_skips_already_scheduled_groups_without_error(self):
        self.client.login(username="manager", password="pw")
        url = reverse("tournaments:stage_generate_all_schedules", kwargs={"pk": self.stage.pk})
        self.client.post(url)
        match_count_before = self.group_a.matches.count() + self.group_b.matches.count()

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        match_count_after = self.group_a.matches.count() + self.group_b.matches.count()
        self.assertEqual(match_count_before, match_count_after)
