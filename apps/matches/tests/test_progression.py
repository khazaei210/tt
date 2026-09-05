from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import (
    NoKnockoutStageError,
    QualifiersNotConfiguredError,
    StageNotCompleteError,
    advance_to_next_stage,
    generate_group_schedule,
    record_set_score,
)
from apps.players.models import Player
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


class AdvanceToNextStageTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.group_stage = Stage.objects.create(
            competition=self.competition,
            name="Groups",
            stage_format=StageFormat.ROUND_ROBIN,
            order=0,
            qualifiers_per_group=2,
        )
        self.knockout_stage = Stage.objects.create(
            competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT, order=1
        )
        self.group_a = Group.objects.create(stage=self.group_stage, name="A", order=0)
        self.group_b = Group.objects.create(stage=self.group_stage, name="B", order=1)
        self.participants = {}
        for group_name, group in (("A", self.group_a), ("B", self.group_b)):
            for i in range(4):
                player = Player.objects.create(first_name=f"{group_name}{i}", last_name="Test", gender="M")
                participant = Participant.objects.create(
                    competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
                )
                GroupParticipant.objects.create(group=group, participant=participant)
                self.participants[f"{group_name}{i}"] = participant

    def _complete_all_group_matches(self):
        for group in (self.group_a, self.group_b):
            generate_group_schedule(group)
        for match in Match.objects.filter(group__in=[self.group_a, self.group_b]):
            # Winner is whichever participant sorts first by pk, for a
            # deterministic and easy-to-reason-about standings order.
            winner, loser = sorted([match.participant_a_id, match.participant_b_id])
            a_score = 11 if match.participant_a_id == winner else 5
            b_score = 5 if match.participant_a_id == winner else 11
            for set_number in (1, 2, 3):
                record_set_score(match, set_number, a_score, b_score)

    def test_advance_brackets_top_qualifiers_from_each_group(self):
        self._complete_all_group_matches()
        advance_to_next_stage(self.group_stage)
        bracket_matches = Match.objects.filter(stage=self.knockout_stage)
        self.assertEqual(bracket_matches.count(), 3)  # 4 qualifiers -> 2 R1 + 1 final
        round1_ids = set()
        for m in bracket_matches.filter(round_number=1):
            round1_ids.add(m.participant_a_id)
            round1_ids.add(m.participant_b_id)
        self.assertEqual(len(round1_ids), 4)

    def test_group_mates_do_not_meet_in_round_one(self):
        self._complete_all_group_matches()
        advance_to_next_stage(self.group_stage)
        group_a_qualifier_ids = set(
            Participant.objects.filter(
                group_assignments__group=self.group_a, id__in=[p.id for p in self.participants.values()]
            ).values_list("id", flat=True)
        )
        for m in Match.objects.filter(stage=self.knockout_stage, round_number=1):
            same_group = {m.participant_a_id, m.participant_b_id} <= group_a_qualifier_ids
            self.assertFalse(same_group, "two qualifiers from the same group met in round 1")

    def test_raises_if_qualifiers_per_group_not_configured(self):
        self.group_stage.qualifiers_per_group = None
        self.group_stage.save()
        self._complete_all_group_matches()
        with self.assertRaises(QualifiersNotConfiguredError):
            advance_to_next_stage(self.group_stage)

    def test_raises_if_stage_not_complete(self):
        generate_group_schedule(self.group_a)
        generate_group_schedule(self.group_b)
        with self.assertRaises(StageNotCompleteError):
            advance_to_next_stage(self.group_stage)

    def test_raises_if_no_knockout_stage_follows(self):
        self.knockout_stage.delete()
        self._complete_all_group_matches()
        with self.assertRaises(NoKnockoutStageError):
            advance_to_next_stage(self.group_stage)
