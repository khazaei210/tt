from django.test import TestCase

from apps.matches.models import Match, MatchStatus
from apps.matches.scoring import ScoreValidationError
from apps.matches.services import (
    InvalidSetNumberError,
    MatchAlreadyCompletedError,
    delete_set_score,
    generate_stage_bracket,
    record_set_score,
)
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    CompetitionRule,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
)


class ScoreServiceTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.rule = CompetitionRule.objects.create(competition=self.competition, best_of_sets=5, points_per_set=11, win_by=2)
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.player_a = Player.objects.create(first_name="A", last_name="Test", gender="M")
        self.player_b = Player.objects.create(first_name="B", last_name="Test", gender="M")
        self.participant_a = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player_a
        )
        self.participant_b = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player_b
        )
        self.match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.participant_a,
            participant_b=self.participant_b,
        )


class RecordSetScoreTests(ScoreServiceTestCase):
    def test_recording_a_set_leaves_match_live_when_not_decided(self):
        record_set_score(self.match, 1, 11, 5)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)
        self.assertIsNone(self.match.winner_id)

    def test_match_completes_once_enough_sets_are_won(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.COMPLETED)
        self.assertEqual(self.match.winner_id, self.participant_a.id)

    def test_other_participant_can_win(self):
        record_set_score(self.match, 1, 5, 11)
        record_set_score(self.match, 2, 8, 11)
        record_set_score(self.match, 3, 9, 11)
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner_id, self.participant_b.id)

    def test_invalid_score_rejected_and_not_persisted(self):
        with self.assertRaises(ScoreValidationError):
            record_set_score(self.match, 1, 11, 10)  # margin too small
        self.assertEqual(self.match.sets.count(), 0)

    def test_set_number_out_of_range_rejected(self):
        with self.assertRaises(InvalidSetNumberError):
            record_set_score(self.match, 6, 11, 5)  # best_of_sets=5, max set is 5

    def test_deciding_set_uses_override_points(self):
        self.rule.deciding_set_points = 7
        self.rule.save()
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 5, 11)
        record_set_score(self.match, 3, 11, 8)
        record_set_score(self.match, 4, 6, 11)
        # Set 5 is the decider: only needs to reach 7, not 11.
        record_set_score(self.match, 5, 7, 5)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.COMPLETED)
        self.assertEqual(self.match.winner_id, self.participant_a.id)

    def test_cannot_edit_completed_match_without_allow_correction(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        with self.assertRaises(MatchAlreadyCompletedError):
            record_set_score(self.match, 3, 9, 11)

    def test_correction_allowed_with_explicit_flag(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner_id, self.participant_a.id)

        # Correct set 3 so participant B actually won it, undoing the sweep.
        record_set_score(self.match, 3, 5, 11, allow_correction=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)
        self.assertIsNone(self.match.winner_id)

    def test_no_rule_configured_falls_back_to_defaults(self):
        self.rule.delete()
        record_set_score(self.match, 1, 11, 5)
        self.match.refresh_from_db()
        self.assertEqual(self.match.sets.get(set_number=1).participant_a_score, 11)


class DeleteSetScoreTests(ScoreServiceTestCase):
    def test_deleting_the_decisive_set_reverts_completion(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.COMPLETED)

        delete_set_score(self.match, 3, allow_correction=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)
        self.assertIsNone(self.match.winner_id)
        self.assertEqual(self.match.sets.count(), 2)

    def test_deleting_from_a_decided_match_requires_allow_correction(self):
        record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 2, 11, 8)
        record_set_score(self.match, 3, 11, 9)
        with self.assertRaises(MatchAlreadyCompletedError):
            delete_set_score(self.match, 3)
        self.assertEqual(self.match.sets.count(), 3)


class KnockoutPropagationTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="KO Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        CompetitionRule.objects.create(competition=self.competition, best_of_sets=3, points_per_set=11, win_by=2)
        self.stage = Stage.objects.create(competition=self.competition, name="KO", stage_format=StageFormat.KNOCKOUT)
        self.participants = []
        for i in range(4):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M")
            self.participants.append(
                Participant.objects.create(
                    competition=self.competition,
                    participant_type=ParticipantType.INDIVIDUAL,
                    individual_player=player,
                    seed=i + 1,
                )
            )
        generate_stage_bracket(self.stage, seeded=True)

    def _win_match(self, match, winner_is_a=True):
        if winner_is_a:
            record_set_score(match, 1, 11, 5)
            record_set_score(match, 2, 11, 5)
        else:
            record_set_score(match, 1, 5, 11)
            record_set_score(match, 2, 5, 11)

    def test_winner_propagates_to_final(self):
        semis = list(Match.objects.filter(stage=self.stage, round_number=1).order_by("bracket_slot"))
        self.assertEqual(len(semis), 2)

        self._win_match(semis[0], winner_is_a=True)
        self._win_match(semis[1], winner_is_a=False)

        final = Match.objects.get(stage=self.stage, round_number=2)
        semis[0].refresh_from_db()
        semis[1].refresh_from_db()
        final.refresh_from_db()
        self.assertEqual(final.participant_a_id, semis[0].winner_id)
        self.assertEqual(final.participant_b_id, semis[1].winner_id)

    def test_correcting_a_semifinal_before_final_is_played_updates_final(self):
        semis = list(Match.objects.filter(stage=self.stage, round_number=1).order_by("bracket_slot"))
        self._win_match(semis[0], winner_is_a=True)
        semis[0].refresh_from_db()
        original_winner_id = semis[0].winner_id

        final = Match.objects.get(stage=self.stage, round_number=2)
        self.assertEqual(final.participant_a_id, original_winner_id)

        # Correct the semifinal: participant B actually won.
        record_set_score(semis[0], 1, 5, 11, allow_correction=True)
        record_set_score(semis[0], 2, 5, 11, allow_correction=True)
        semis[0].refresh_from_db()
        final.refresh_from_db()
        self.assertEqual(final.participant_a_id, semis[0].winner_id)
        self.assertNotEqual(final.participant_a_id, original_winner_id)

    def test_reverting_semifinal_completion_clears_untouched_final_slot(self):
        semis = list(Match.objects.filter(stage=self.stage, round_number=1).order_by("bracket_slot"))
        self._win_match(semis[0], winner_is_a=True)
        final = Match.objects.get(stage=self.stage, round_number=2)
        final.refresh_from_db()
        self.assertIsNotNone(final.participant_a_id)

        delete_set_score(semis[0], 2, allow_correction=True)  # back to 1-0, no longer decided (best of 3 needs 2)
        final.refresh_from_db()
        self.assertIsNone(final.participant_a_id)
