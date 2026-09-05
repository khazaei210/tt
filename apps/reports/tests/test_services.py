from django.test import TestCase

from apps.matches.services import generate_stage_bracket, record_set_score
from apps.players.models import DoublesPair, Player
from apps.reports.services import build_player_statistics, build_tournament_report
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament


class PlayerStatisticsTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.player = Player.objects.create(first_name="Star", last_name="Player", gender="M")
        self.opponent1 = Player.objects.create(first_name="Opp", last_name="One", gender="M")
        self.opponent2 = Player.objects.create(first_name="Opp", last_name="Two", gender="M")
        self.participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.player
        )
        self.opp1_participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.opponent1
        )
        self.opp2_participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.opponent2
        )

    def _make_match(self, round_number, a, b):
        from apps.matches.models import Match

        return Match.objects.create(
            competition=self.competition, stage=self.stage, round_number=round_number, participant_a=a, participant_b=b
        )

    def test_player_with_no_matches(self):
        stats = build_player_statistics(self.player)
        self.assertEqual(stats.matches_played, 0)
        self.assertEqual(stats.win_percentage, 0)

    def test_win_and_loss_are_counted_from_the_players_own_side(self):
        win_match = self._make_match(1, self.participant, self.opp1_participant)
        record_set_score(win_match, 1, 11, 5)
        record_set_score(win_match, 2, 11, 5)
        record_set_score(win_match, 3, 11, 5)

        # This time the player is on the "b" side and loses.
        loss_match = self._make_match(2, self.opp2_participant, self.participant)
        record_set_score(loss_match, 1, 11, 3)
        record_set_score(loss_match, 2, 11, 3)
        record_set_score(loss_match, 3, 11, 3)

        stats = build_player_statistics(self.player)
        self.assertEqual(stats.matches_played, 2)
        self.assertEqual(stats.wins, 1)
        self.assertEqual(stats.losses, 1)
        self.assertEqual(stats.win_percentage, 50)
        self.assertEqual(stats.sets_won, 3)  # 3-0 sweep in the win
        self.assertEqual(stats.sets_lost, 3)  # 0-3 sweep in the loss
        self.assertEqual(stats.points_scored, 11 + 11 + 11 + 3 + 3 + 3)
        self.assertEqual(stats.points_conceded, 5 + 5 + 5 + 11 + 11 + 11)

    def test_in_progress_match_is_excluded(self):
        match = self._make_match(1, self.participant, self.opp1_participant)
        record_set_score(match, 1, 11, 5)  # only one set — not decided yet
        stats = build_player_statistics(self.player)
        self.assertEqual(stats.matches_played, 0)

    def test_doubles_participant_credits_both_players(self):
        doubles_competition = Competition.objects.create(
            tournament=self.tournament, name="Doubles", participant_type=ParticipantType.DOUBLES
        )
        doubles_stage = Stage.objects.create(
            competition=doubles_competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        partner = Player.objects.create(first_name="Partner", last_name="Player", gender="M")
        pair = DoublesPair.objects.create(player_one=self.player, player_two=partner)
        pair_participant = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair
        )
        opponent_pair = DoublesPair.objects.create(player_one=self.opponent1, player_two=self.opponent2)
        opponent_participant = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=opponent_pair
        )

        from apps.matches.models import Match

        match = Match.objects.create(
            competition=doubles_competition,
            stage=doubles_stage,
            round_number=1,
            participant_a=pair_participant,
            participant_b=opponent_participant,
        )
        record_set_score(match, 1, 11, 5)
        record_set_score(match, 2, 11, 5)
        record_set_score(match, 3, 11, 5)

        self.assertEqual(build_player_statistics(self.player).wins, 1)
        self.assertEqual(build_player_statistics(partner).wins, 1)


class TournamentReportTests(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")

    def test_competition_with_no_matches(self):
        Competition.objects.create(tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL)
        report = build_tournament_report(self.tournament)
        self.assertEqual(len(report.competitions), 1)
        row = report.competitions[0]
        self.assertEqual(row.matches_total, 0)
        self.assertEqual(row.completion_percent, 0)
        self.assertEqual(row.placements, [])

    def test_completed_knockout_reports_placements_and_completion(self):
        competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        stage = Stage.objects.create(competition=competition, name="Knockout", stage_format=StageFormat.KNOCKOUT)
        participants = []
        for i in range(4):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M")
            participants.append(
                Participant.objects.create(
                    competition=competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player, seed=i + 1
                )
            )
        generate_stage_bracket(stage, seeded=True)

        from apps.matches.models import Match, MatchStatus

        while True:
            pending = (
                Match.objects.filter(stage=stage, status__in=[MatchStatus.SCHEDULED, MatchStatus.READY, MatchStatus.LIVE])
                .exclude(participant_a__isnull=True)
                .exclude(participant_b__isnull=True)
            )
            if not pending.exists():
                break
            for match in pending:
                winner_id, _loser_id = sorted([match.participant_a_id, match.participant_b_id])
                a_score = 11 if match.participant_a_id == winner_id else 5
                b_score = 5 if match.participant_a_id == winner_id else 11
                for set_number in (1, 2, 3):
                    record_set_score(match, set_number, a_score, b_score)

        report = build_tournament_report(self.tournament)
        row = report.competitions[0]
        self.assertEqual(row.matches_total, 3)
        self.assertEqual(row.matches_decided, 3)
        self.assertEqual(row.completion_percent, 100)
        # 4 participants, no third-place match: placements are 1, 2, 3, 3 —
        # both semifinal losers tie at 3rd, so all four fall within "top 3".
        self.assertEqual(len(row.placements), 4)
        self.assertEqual(row.placements[0][0], 1)
        self.assertEqual(row.placements[0][1], participants[0])
