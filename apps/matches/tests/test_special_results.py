from django.test import TestCase

from apps.matches.models import Match, MatchStatus
from apps.matches.services import (
    InvalidOfficialRoleError,
    InvalidWinnerError,
    MatchAlreadyCompletedError,
    claim_match,
    generate_stage_bracket,
    record_default,
    record_retirement,
    record_set_score,
    record_walkover,
    start_match,
)
from apps.players.models import Player
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament

from django.contrib.auth import get_user_model

User = get_user_model()


class SpecialResultServiceTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.player_a = Player.objects.create(first_name="A", last_name="Test", gender="M")
        self.player_b = Player.objects.create(first_name="B", last_name="Test", gender="M")
        self.player_c = Player.objects.create(first_name="C", last_name="Test", gender="M")
        self.participant_a = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player_a
        )
        self.participant_b = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player_b
        )
        self.participant_c = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player_c
        )
        self.match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=self.participant_a,
            participant_b=self.participant_b,
        )


class StartMatchTests(SpecialResultServiceTestCase):
    def test_start_sets_live_and_stamps_start_time(self):
        start_match(self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)
        self.assertIsNotNone(self.match.start_time)

    def test_starting_twice_keeps_original_start_time(self):
        start_match(self.match)
        self.match.refresh_from_db()
        first_start = self.match.start_time
        start_match(self.match)
        self.match.refresh_from_db()
        self.assertEqual(self.match.start_time, first_start)

    def test_cannot_start_a_decided_match(self):
        record_walkover(self.match, self.participant_a.id)
        with self.assertRaises(MatchAlreadyCompletedError):
            start_match(self.match)


class RecordWalkoverRetirementDefaultTests(SpecialResultServiceTestCase):
    def test_walkover_sets_winner_and_status(self):
        record_walkover(self.match, self.participant_a.id)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.WALKOVER)
        self.assertEqual(self.match.winner_id, self.participant_a.id)
        self.assertIsNotNone(self.match.end_time)

    def test_retirement_sets_winner_and_status(self):
        record_retirement(self.match, self.participant_b.id)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.RETIRED)
        self.assertEqual(self.match.winner_id, self.participant_b.id)

    def test_default_sets_winner_and_status(self):
        record_default(self.match, self.participant_a.id)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.DEFAULT)

    def test_winner_must_be_one_of_the_two_participants(self):
        with self.assertRaises(InvalidWinnerError):
            record_walkover(self.match, self.participant_c.id)

    def test_cannot_overwrite_a_decided_match_without_allow_correction(self):
        record_walkover(self.match, self.participant_a.id)
        with self.assertRaises(MatchAlreadyCompletedError):
            record_retirement(self.match, self.participant_b.id)

    def test_allow_correction_overwrites_a_decided_match(self):
        record_walkover(self.match, self.participant_a.id)
        record_retirement(self.match, self.participant_b.id, allow_correction=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.RETIRED)
        self.assertEqual(self.match.winner_id, self.participant_b.id)

    def test_walkover_propagates_winner_to_next_knockout_match(self):
        knockout_stage = Stage.objects.create(
            competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT, order=1
        )
        generate_stage_bracket(knockout_stage, seeded=True, participant_ids=[
            self.participant_a.id, self.participant_b.id, self.participant_c.id,
            Participant.objects.create(
                competition=self.competition, participant_type=ParticipantType.INDIVIDUAL,
                individual_player=Player.objects.create(first_name="D", last_name="Test", gender="M"),
            ).id,
        ])
        from django.db.models import Q

        round1_match = Match.objects.get(
            Q(participant_a=self.participant_a) | Q(participant_b=self.participant_a),
            stage=knockout_stage,
            round_number=1,
        )
        record_walkover(round1_match, self.participant_a.id)
        final = Match.objects.get(stage=knockout_stage, round_number=2)
        self.assertIn(self.participant_a.id, (final.participant_a_id, final.participant_b_id))

    def test_recording_a_set_score_on_a_walkover_requires_correction(self):
        record_walkover(self.match, self.participant_a.id)
        with self.assertRaises(MatchAlreadyCompletedError):
            record_set_score(self.match, 1, 11, 5)
        record_set_score(self.match, 1, 11, 5, allow_correction=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)


class ClaimMatchTests(SpecialResultServiceTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="ref1", password="pw")

    def test_claim_as_referee(self):
        claim_match(self.match, self.user, "referee")
        self.match.refresh_from_db()
        self.assertEqual(self.match.referee_id, self.user.id)

    def test_claim_as_scorekeeper(self):
        claim_match(self.match, self.user, "scorekeeper")
        self.match.refresh_from_db()
        self.assertEqual(self.match.scorekeeper_id, self.user.id)

    def test_invalid_role_raises(self):
        with self.assertRaises(InvalidOfficialRoleError):
            claim_match(self.match, self.user, "coach")
