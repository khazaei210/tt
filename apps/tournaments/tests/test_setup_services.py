from django.test import TestCase

from apps.players.models import Player
from apps.rankings.models import EloRating
from apps.rankings.services import get_default_ranking_category
from apps.tournaments.models import (
    Competition,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
    TournamentAuditLog,
)
from apps.tournaments.services.setup import (
    DuplicateGroupAssignmentError,
    InvalidGroupMoveError,
    NoGroupsAvailableError,
    NotRoundRobinStageError,
    StageLockedError,
    auto_assign_participants_to_groups,
    create_groups,
    move_participant_to_group,
    seed_participants_by_rating,
    suggested_group_count,
)


def make_player(i):
    return Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900000{i:04d}")


class SeedByRatingTests(TestCase):
    def setUp(self):
        self.category = get_default_ranking_category()
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament,
            name="Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            ranking_category=self.category,
        )

    def _add_participant(self, player, rating=None):
        participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
        )
        if rating is not None:
            EloRating.objects.create(player=player, category=self.category, rating=rating)
        return participant

    def test_higher_rating_gets_a_lower_seed_number(self):
        low = self._add_participant(make_player(1), rating=1400)
        high = self._add_participant(make_player(2), rating=1800)
        mid = self._add_participant(make_player(3), rating=1600)

        seed_participants_by_rating(self.competition)

        high.refresh_from_db()
        mid.refresh_from_db()
        low.refresh_from_db()
        self.assertEqual(high.seed, 1)
        self.assertEqual(mid.seed, 2)
        self.assertEqual(low.seed, 3)

    def test_unrated_participants_seeded_after_rated_ones(self):
        rated = self._add_participant(make_player(1), rating=1500)
        unrated = self._add_participant(make_player(2))

        seed_participants_by_rating(self.competition)

        rated.refresh_from_db()
        unrated.refresh_from_db()
        self.assertEqual(rated.seed, 1)
        self.assertEqual(unrated.seed, 2)

    def test_overwrites_an_existing_manual_seed(self):
        participant = self._add_participant(make_player(1), rating=1500)
        participant.seed = 99
        participant.save(update_fields=["seed"])

        seed_participants_by_rating(self.competition)

        participant.refresh_from_db()
        self.assertEqual(participant.seed, 1)

    def test_bye_participants_are_not_seeded(self):
        Participant.objects.create(competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, is_bye=True)
        rated = self._add_participant(make_player(1), rating=1500)

        result = seed_participants_by_rating(self.competition)

        self.assertEqual(len(result), 1)
        rated.refresh_from_db()
        self.assertEqual(rated.seed, 1)


class AutoAssignToGroupsTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.participants = []
        for i, seed in enumerate((1, 2, 3, 4)):
            p = Participant.objects.create(
                competition=self.competition,
                participant_type=ParticipantType.INDIVIDUAL,
                individual_player=make_player(i),
                seed=seed,
            )
            self.participants.append(p)

    def test_raises_when_stage_has_no_groups(self):
        with self.assertRaises(NoGroupsAvailableError):
            auto_assign_participants_to_groups(self.stage)

    def test_raises_for_a_knockout_stage(self):
        knockout = Stage.objects.create(
            competition=self.competition, name="Bracket", stage_format=StageFormat.KNOCKOUT, order=2
        )
        with self.assertRaises(NotRoundRobinStageError):
            auto_assign_participants_to_groups(knockout)

    def test_distributes_evenly_in_seed_order_across_two_groups(self):
        group_a = Group.objects.create(stage=self.stage, name="A", order=1)
        group_b = Group.objects.create(stage=self.stage, name="B", order=2)

        auto_assign_participants_to_groups(self.stage)

        a_seeds = sorted(
            GroupParticipant.objects.filter(group=group_a).values_list("participant__seed", flat=True)
        )
        b_seeds = sorted(
            GroupParticipant.objects.filter(group=group_b).values_list("participant__seed", flat=True)
        )
        self.assertEqual(a_seeds, [1, 3])
        self.assertEqual(b_seeds, [2, 4])

    def test_does_not_reassign_a_participant_already_in_a_group(self):
        group_a = Group.objects.create(stage=self.stage, name="A", order=1)
        group_b = Group.objects.create(stage=self.stage, name="B", order=2)
        GroupParticipant.objects.create(group=group_b, participant=self.participants[0])

        auto_assign_participants_to_groups(self.stage)

        self.assertTrue(GroupParticipant.objects.filter(group=group_b, participant=self.participants[0]).exists())
        self.assertEqual(GroupParticipant.objects.filter(participant=self.participants[0]).count(), 1)
        # Every participant ends up placed exactly once.
        self.assertEqual(GroupParticipant.objects.filter(group__stage=self.stage).count(), 4)

    def test_no_op_when_everyone_is_already_assigned(self):
        group_a = Group.objects.create(stage=self.stage, name="A", order=1)
        for p in self.participants:
            GroupParticipant.objects.create(group=group_a, participant=p)

        created = auto_assign_participants_to_groups(self.stage)

        self.assertEqual(created, [])

    def test_raises_when_stage_is_locked(self):
        Group.objects.create(stage=self.stage, name="A", order=1)
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        with self.assertRaises(StageLockedError):
            auto_assign_participants_to_groups(self.stage)


class SuggestedGroupCountTests(TestCase):
    def test_rounds_up_to_fit_the_default_group_size(self):
        self.assertEqual(suggested_group_count(0), 1)
        self.assertEqual(suggested_group_count(4), 1)
        self.assertEqual(suggested_group_count(5), 2)
        self.assertEqual(suggested_group_count(16), 4)

    def test_respects_a_custom_target_group_size(self):
        self.assertEqual(suggested_group_count(9, target_group_size=3), 3)


class CreateGroupsTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )

    def test_creates_the_requested_number_of_groups_named_sequentially(self):
        created = create_groups(self.stage, 3)
        self.assertEqual(len(created), 3)
        names = list(self.stage.groups.order_by("order").values_list("name", flat=True))
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names)), 3)

    def test_continues_numbering_after_existing_groups(self):
        Group.objects.create(stage=self.stage, name="Group A", order=1)
        created = create_groups(self.stage, 1)
        self.assertEqual(len(created), 1)
        self.assertNotEqual(created[0].name, "Group A")
        self.assertEqual(self.stage.groups.count(), 2)

    def test_raises_for_a_knockout_stage(self):
        knockout = Stage.objects.create(
            competition=self.competition, name="Bracket", stage_format=StageFormat.KNOCKOUT, order=2
        )
        with self.assertRaises(NotRoundRobinStageError):
            create_groups(knockout, 2)

    def test_raises_when_stage_is_locked(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        with self.assertRaises(StageLockedError):
            create_groups(self.stage, 2)

    def test_logs_an_audit_entry(self):
        create_groups(self.stage, 2)
        self.assertTrue(TournamentAuditLog.objects.filter(tournament=self.tournament).exists())


class MoveParticipantToGroupTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        self.other_stage = Stage.objects.create(
            competition=self.competition, name="Other", stage_format=StageFormat.ROUND_ROBIN, order=2
        )
        self.group_a = Group.objects.create(stage=self.stage, name="A", order=1)
        self.group_b = Group.objects.create(stage=self.stage, name="B", order=2)
        self.other_stage_group = Group.objects.create(stage=self.other_stage, name="C", order=1)
        self.participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=make_player(1)
        )
        self.group_participant = GroupParticipant.objects.create(group=self.group_a, participant=self.participant)

    def test_moves_the_participant_to_the_target_group(self):
        move_participant_to_group(self.group_participant, self.group_b)
        self.group_participant.refresh_from_db()
        self.assertEqual(self.group_participant.group_id, self.group_b.id)

    def test_rejects_moving_to_the_same_group(self):
        with self.assertRaises(InvalidGroupMoveError):
            move_participant_to_group(self.group_participant, self.group_a)

    def test_rejects_a_group_from_a_different_stage(self):
        with self.assertRaises(InvalidGroupMoveError):
            move_participant_to_group(self.group_participant, self.other_stage_group)

    def test_rejects_a_duplicate_assignment(self):
        # Same participant already has a (stray) GroupParticipant row in the target group.
        GroupParticipant.objects.create(group=self.group_b, participant=self.participant)
        with self.assertRaises(DuplicateGroupAssignmentError):
            move_participant_to_group(self.group_participant, self.group_b)

    def test_rejects_when_stage_is_locked(self):
        self.stage.is_locked = True
        self.stage.save(update_fields=["is_locked"])
        with self.assertRaises(StageLockedError):
            move_participant_to_group(self.group_participant, self.group_b)

    def test_logs_an_audit_entry(self):
        move_participant_to_group(self.group_participant, self.group_b)
        self.assertTrue(TournamentAuditLog.objects.filter(tournament=self.tournament).exists())
