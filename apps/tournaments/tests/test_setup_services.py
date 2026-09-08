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
)
from apps.tournaments.services.setup import (
    NoGroupsAvailableError,
    NotRoundRobinStageError,
    auto_assign_participants_to_groups,
    seed_participants_by_rating,
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
