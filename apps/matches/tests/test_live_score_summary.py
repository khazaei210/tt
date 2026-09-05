from django.test import TestCase

from apps.matches.models import Match, MatchSet
from apps.matches.services import summarize_live_score
from apps.players.models import Player
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament


class SummarizeLiveScoreTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.participant_a = Participant.objects.create(
            competition=self.competition,
            participant_type=ParticipantType.INDIVIDUAL,
            individual_player=Player.objects.create(first_name="A", last_name="Test", gender="M"),
        )
        self.participant_b = Participant.objects.create(
            competition=self.competition,
            participant_type=ParticipantType.INDIVIDUAL,
            individual_player=Player.objects.create(first_name="B", last_name="Test", gender="M"),
        )
        self.match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.participant_a,
            participant_b=self.participant_b,
        )

    def test_none_when_no_sets_recorded(self):
        self.assertIsNone(summarize_live_score(self.match))

    def test_sets_score_and_last_set_after_one_set(self):
        MatchSet.objects.create(match=self.match, set_number=1, participant_a_score=11, participant_b_score=8)
        summary = summarize_live_score(self.match)
        self.assertEqual(summary.sets_score, "1-0")
        self.assertEqual(summary.last_set_score, "11-8")

    def test_last_set_is_the_most_recently_numbered_one(self):
        MatchSet.objects.create(match=self.match, set_number=1, participant_a_score=11, participant_b_score=8)
        MatchSet.objects.create(match=self.match, set_number=2, participant_a_score=9, participant_b_score=11)
        MatchSet.objects.create(match=self.match, set_number=3, participant_a_score=4, participant_b_score=11)
        summary = summarize_live_score(self.match)
        self.assertEqual(summary.sets_score, "1-2")
        self.assertEqual(summary.last_set_score, "4-11")
