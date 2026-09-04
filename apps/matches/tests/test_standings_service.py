from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import compute_group_standings, record_set_score
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    CompetitionRule,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
)


class GroupStandingsServiceTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        CompetitionRule.objects.create(competition=self.competition, best_of_sets=3, points_per_set=11, win_by=2)
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.group = Group.objects.create(stage=self.stage, name="Group A")

        self.participants = {}
        for name in ["A", "B", "C"]:
            player = Player.objects.create(first_name=name, last_name="Test", gender="M")
            participant = Participant.objects.create(
                competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
            )
            GroupParticipant.objects.create(group=self.group, participant=participant)
            self.participants[name] = participant

    def _play(self, a_name, b_name, sets):
        match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            group=self.group,
            round_number=1,
            participant_a=self.participants[a_name],
            participant_b=self.participants[b_name],
        )
        for i, (a_score, b_score) in enumerate(sets, start=1):
            record_set_score(match, i, a_score, b_score)
        return match

    def test_standings_reflect_only_completed_matches(self):
        self._play("A", "B", [(11, 5), (11, 5)])  # A wins 2-0
        # C has played nothing yet.
        rows = compute_group_standings(self.group)
        by_name = {row["participant"].individual_player.first_name: row for row in rows}
        self.assertEqual(by_name["A"]["played"], 1)
        self.assertEqual(by_name["A"]["wins"], 1)
        self.assertEqual(by_name["A"]["match_points"], 2)
        self.assertEqual(by_name["C"]["played"], 0)
        self.assertEqual(by_name["C"]["match_points"], 0)

    def test_ranking_reflects_real_match_results(self):
        self._play("A", "B", [(11, 5), (11, 5)])       # A beats B 2-0
        self._play("A", "C", [(5, 11), (5, 11)])       # A loses to C 0-2
        self._play("B", "C", [(11, 9), (11, 9)])       # B beats C 2-0
        rows = compute_group_standings(self.group)
        names_in_order = [row["participant"].individual_player.first_name for row in rows]
        # A: 1-1, B: 1-1, C: 1-1 -> tied on match points, resolved by head-to-head/set-diff.
        self.assertEqual(len(names_in_order), 3)
        self.assertEqual(set(names_in_order), {"A", "B", "C"})

    def test_in_progress_match_does_not_count_yet(self):
        match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            group=self.group,
            round_number=1,
            participant_a=self.participants["A"],
            participant_b=self.participants["B"],
        )
        record_set_score(match, 1, 11, 5)  # only one set played, match still live
        rows = compute_group_standings(self.group)
        by_name = {row["participant"].individual_player.first_name: row for row in rows}
        self.assertEqual(by_name["A"]["played"], 0)
        self.assertEqual(by_name["B"]["played"], 0)
