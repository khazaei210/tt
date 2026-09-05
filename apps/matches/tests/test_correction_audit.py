from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.matches.models import Match, MatchCorrection, MatchCorrectionAction, MatchStatus
from apps.matches.services import (
    delete_set_score,
    record_set_score,
    record_walkover,
)
from apps.players.models import Player
from apps.tournaments.models import Competition, CompetitionRule, Participant, ParticipantType, Stage, StageFormat, Tournament

User = get_user_model()


class CorrectionAuditTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        CompetitionRule.objects.create(competition=self.competition, best_of_sets=5, points_per_set=11, win_by=2)
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
        self.referee = User.objects.create_user(username="ref1", password="pw")


class SetScoreCorrectionAuditTests(CorrectionAuditTestCase):
    def test_first_time_entry_is_not_logged_as_a_correction(self):
        record_set_score(self.match, 1, 11, 5, performed_by=self.referee)
        self.assertEqual(MatchCorrection.objects.filter(match=self.match).count(), 0)

    def test_overwriting_an_existing_set_logs_a_correction(self):
        record_set_score(self.match, 1, 11, 5, performed_by=self.referee)
        record_set_score(self.match, 1, 11, 9, performed_by=self.referee)
        correction = MatchCorrection.objects.get(match=self.match, action=MatchCorrectionAction.SET_SCORE_CHANGED)
        self.assertEqual(correction.set_number, 1)
        self.assertEqual(correction.previous_value, "11-5")
        self.assertEqual(correction.new_value, "11-9")
        self.assertEqual(correction.performed_by, self.referee)

    def test_resaving_the_same_score_does_not_log_a_correction(self):
        record_set_score(self.match, 1, 11, 5, performed_by=self.referee)
        record_set_score(self.match, 1, 11, 5, performed_by=self.referee)
        self.assertEqual(MatchCorrection.objects.filter(match=self.match).count(), 0)

    def test_correcting_a_decided_match_logs_a_result_correction(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        record_set_score(self.match, 3, 5, 11, allow_correction=True, performed_by=self.referee)

        result_correction = MatchCorrection.objects.get(
            match=self.match, action=MatchCorrectionAction.RESULT_CORRECTED
        )
        self.assertIn(self.participant_a.display_name, result_correction.previous_value)
        self.assertNotIn(self.participant_a.display_name, result_correction.new_value)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)
        # Both the per-set change and the overall result change are logged.
        self.assertTrue(
            MatchCorrection.objects.filter(match=self.match, action=MatchCorrectionAction.SET_SCORE_CHANGED).exists()
        )

    def test_deleting_a_set_logs_a_correction(self):
        record_set_score(self.match, 1, 11, 5)
        delete_set_score(self.match, 1, performed_by=self.referee)
        correction = MatchCorrection.objects.get(match=self.match, action=MatchCorrectionAction.SET_SCORE_DELETED)
        self.assertEqual(correction.previous_value, "11-5")
        self.assertEqual(correction.new_value, "")
        self.assertEqual(correction.performed_by, self.referee)

    def test_deleting_a_nonexistent_set_logs_nothing(self):
        delete_set_score(self.match, 1, performed_by=self.referee)
        self.assertEqual(MatchCorrection.objects.filter(match=self.match).count(), 0)


class ResultCorrectionAuditTests(CorrectionAuditTestCase):
    def test_first_walkover_is_not_logged_as_a_correction(self):
        record_walkover(self.match, self.participant_a.id, performed_by=self.referee)
        self.assertEqual(MatchCorrection.objects.filter(match=self.match).count(), 0)

    def test_correcting_a_walkover_logs_a_result_correction(self):
        record_walkover(self.match, self.participant_a.id)
        record_walkover(self.match, self.participant_b.id, allow_correction=True, performed_by=self.referee)
        correction = MatchCorrection.objects.get(match=self.match, action=MatchCorrectionAction.RESULT_CORRECTED)
        self.assertIn(self.participant_a.display_name, correction.previous_value)
        self.assertIn(self.participant_b.display_name, correction.new_value)
        self.assertEqual(correction.performed_by, self.referee)
