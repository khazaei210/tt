from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.services import generate_stage_bracket
from apps.players.models import Player
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
    TournamentAuditLog,
    TournamentStaff,
)

User = get_user_model()


def make_player(i):
    return Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900002{i:04d}")


class StageLockingViewTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.participants = [
            Participant.objects.create(
                competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=make_player(i)
            )
            for i in range(4)
        ]
        self.group = Group.objects.create(stage=self.stage, name="A", order=1)

    def test_only_a_manager_can_lock(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("tournaments:stage_lock", kwargs={"pk": self.stage.pk}))
        self.assertEqual(response.status_code, 403)
        self.stage.refresh_from_db()
        self.assertFalse(self.stage.is_locked)

    def test_manager_can_lock_and_unlock(self):
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:stage_lock", kwargs={"pk": self.stage.pk}))
        self.stage.refresh_from_db()
        self.assertTrue(self.stage.is_locked)

        self.client.post(reverse("tournaments:stage_unlock", kwargs={"pk": self.stage.pk}))
        self.stage.refresh_from_db()
        self.assertFalse(self.stage.is_locked)

    def test_locking_logs_audit_entries(self):
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:stage_lock", kwargs={"pk": self.stage.pk}))
        self.client.post(reverse("tournaments:stage_unlock", kwargs={"pk": self.stage.pk}))
        actions = set(TournamentAuditLog.objects.filter(tournament=self.tournament).values_list("action", flat=True))
        self.assertIn("stage_locked", actions)
        self.assertIn("stage_unlocked", actions)

    def test_locked_stage_blocks_auto_assign(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:stage_auto_assign_groups", kwargs={"pk": self.stage.pk}))
        self.assertEqual(GroupParticipant.objects.count(), 0)

    def test_locked_stage_blocks_bulk_group_create(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:stage_groups_bulk_create", kwargs={"pk": self.stage.pk}), {"count": 2}
        )
        self.assertEqual(self.stage.groups.count(), 1)

    def test_locked_stage_blocks_group_participant_add(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:group_participant_add", kwargs={"pk": self.group.pk}),
            {"participant": self.participants[0].pk},
        )
        self.assertEqual(GroupParticipant.objects.count(), 0)

    def test_locked_stage_blocks_group_participant_remove(self):
        gp = GroupParticipant.objects.create(group=self.group, participant=self.participants[0])
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:group_participant_remove", kwargs={"pk": self.group.pk, "group_participant_id": gp.pk})
        )
        self.assertTrue(GroupParticipant.objects.filter(pk=gp.pk).exists())

    def test_locked_stage_blocks_group_participant_move(self):
        other_group = Group.objects.create(stage=self.stage, name="B", order=2)
        gp = GroupParticipant.objects.create(group=self.group, participant=self.participants[0])
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:group_participant_move", kwargs={"pk": self.group.pk, "group_participant_id": gp.pk}),
            {"target_group": other_group.pk},
        )
        gp.refresh_from_db()
        self.assertEqual(gp.group_id, self.group.id)

    def test_locked_stage_blocks_group_create_view(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:group_add", kwargs={"stage_pk": self.stage.pk}), {"name": "New", "order": 3})
        self.assertEqual(self.stage.groups.count(), 1)

    def test_locked_stage_blocks_group_delete(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        response = self.client.post(reverse("tournaments:group_delete", kwargs={"pk": self.group.pk}))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())


class KnockoutStageLockingTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER)
        self.stage = Stage.objects.create(
            competition=self.competition, name="Bracket", stage_format=StageFormat.KNOCKOUT
        )
        self.participants = [
            Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=make_player(i),
                seed=i + 1,
            )
            for i in range(4)
        ]

    def test_locked_stage_blocks_bracket_generate(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:stage_bracket_generate", kwargs={"pk": self.stage.pk}))
        self.assertFalse(self.stage.matches.exists())

    def test_locked_stage_blocks_bracket_clear(self):
        generate_stage_bracket(self.stage, seeded=True)
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(reverse("tournaments:stage_bracket_clear", kwargs={"pk": self.stage.pk}))
        self.assertTrue(self.stage.matches.exists())

    def test_locked_stage_blocks_bracket_swap(self):
        generate_stage_bracket(self.stage, seeded=True)
        round_one = list(self.stage.matches.filter(round_number=1).order_by("bracket_slot"))
        a_id, b_id = round_one[0].participant_a_id, round_one[1].participant_a_id
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:stage_bracket_swap", kwargs={"pk": self.stage.pk}),
            {"participant_a": a_id, "participant_b": b_id},
        )
        round_one[0].refresh_from_db()
        round_one[1].refresh_from_db()
        self.assertEqual(round_one[0].participant_a_id, a_id)
        self.assertEqual(round_one[1].participant_a_id, b_id)
