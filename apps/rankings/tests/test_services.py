from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import generate_stage_bracket, record_set_score
from apps.players.models import Player
from apps.rankings.elo import DEFAULT_ELO_RATING
from apps.rankings.models import EloRating, PlayerRanking, RankingCategory, RankingEvent, RankingPointsScale
from apps.rankings.services import (
    PlacementsNotAvailableError,
    RankingCategoryNotConfiguredError,
    award_ranking_points,
    build_category_leaderboard,
    determine_final_placements,
)
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament


class RankingServiceTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Test Open")
        self.category = RankingCategory.objects.create(name="Men's Singles")
        for placement, points in ((1, 100), (2, 60), (3, 40), (5, 20)):
            RankingPointsScale.objects.create(category=self.category, placement=placement, points=points)
        self.competition = Competition.objects.create(
            tournament=self.tournament,
            name="Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            ranking_category=self.category,
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT
        )
        self.participants = []
        for i in range(8):
            player = Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900002{i:04d}")
            self.participants.append(
                Participant.objects.create(
                    competition=self.competition,
                    participant_type=ParticipantType.INDIVIDUAL,
                    individual_player=player,
                    seed=i + 1,
                )
            )

    def _play_out_bracket(self, *, third_place=False):
        generate_stage_bracket(self.stage, seeded=True, third_place=third_place)
        # Repeatedly complete every match whose participants are both known,
        # with the lower-seeded (smaller pk) participant always winning,
        # until the whole bracket (including any third-place match) is
        # decided.
        while True:
            pending = Match.objects.filter(stage=self.stage, status__in=["scheduled", "ready", "live"]).exclude(
                participant_a__isnull=True
            ).exclude(participant_b__isnull=True)
            if not pending.exists():
                break
            for match in pending:
                winner_id, loser_id = sorted([match.participant_a_id, match.participant_b_id])
                a_score = 11 if match.participant_a_id == winner_id else 5
                b_score = 5 if match.participant_a_id == winner_id else 11
                for set_number in (1, 2, 3):
                    record_set_score(match, set_number, a_score, b_score)

    def test_placements_without_third_place_match_tie_semifinal_losers(self):
        self._play_out_bracket(third_place=False)
        placements = determine_final_placements(self.competition)
        champion = self.participants[0].id
        self.assertEqual(placements[champion], 1)
        semifinal_losers = [pid for pid, place in placements.items() if place == 3]
        self.assertEqual(len(semifinal_losers), 2)
        quarterfinal_losers = [pid for pid, place in placements.items() if place == 5]
        self.assertEqual(len(quarterfinal_losers), 4)

    def test_placements_with_third_place_match_splits_three_and_four(self):
        self._play_out_bracket(third_place=True)
        placements = determine_final_placements(self.competition)
        self.assertEqual(len([p for p in placements.values() if p == 3]), 1)
        self.assertEqual(len([p for p in placements.values() if p == 4]), 1)

    def test_placements_not_available_before_bracket_completes(self):
        generate_stage_bracket(self.stage, seeded=True)
        with self.assertRaises(PlacementsNotAvailableError):
            determine_final_placements(self.competition)

    def test_award_ranking_points_creates_events_and_updates_totals(self):
        self._play_out_bracket(third_place=False)
        events = award_ranking_points(self.competition)
        self.assertEqual(len(events), 8)

        champion_player = self.participants[0].individual_player
        ranking = PlayerRanking.objects.get(player=champion_player, category=self.category)
        self.assertEqual(ranking.points, 100)
        self.assertEqual(ranking.current_rank, 1)

        # A quarterfinal loser (tied at 5th) still gets the configured points.
        loser_player = self.participants[7].individual_player
        loser_ranking = PlayerRanking.objects.get(player=loser_player, category=self.category)
        self.assertEqual(loser_ranking.points, 20)

    def test_award_ranking_points_is_idempotent(self):
        self._play_out_bracket(third_place=False)
        award_ranking_points(self.competition)
        second_events = award_ranking_points(self.competition)
        self.assertEqual(len(second_events), 0)
        champion_player = self.participants[0].individual_player
        self.assertEqual(RankingEvent.objects.filter(player=champion_player, competition=self.competition).count(), 1)

    def test_raises_without_ranking_category(self):
        self.competition.ranking_category = None
        self.competition.save()
        self._play_out_bracket(third_place=False)
        with self.assertRaises(RankingCategoryNotConfiguredError):
            award_ranking_points(self.competition)


class CategoryLeaderboardTests(RankingServiceTestCase):
    def test_empty_category_returns_no_rows(self):
        empty_category = RankingCategory.objects.create(name="Empty")
        self.assertEqual(build_category_leaderboard(empty_category), [])

    def test_merges_elo_and_points_for_the_same_player(self):
        self._play_out_bracket(third_place=False)
        award_ranking_points(self.competition)

        champion = self.participants[0].individual_player
        rows_by_player = {row.player.pk: row for row in build_category_leaderboard(self.category)}

        champion_row = rows_by_player[champion.pk]
        self.assertEqual(champion_row.points, 100)
        self.assertIsNotNone(champion_row.rating)
        self.assertGreater(champion_row.rating, DEFAULT_ELO_RATING)
        self.assertEqual(champion_row.wins, 3)  # 3 rounds in an 8-player bracket
        self.assertEqual(champion_row.losses, 0)
        self.assertEqual(champion_row.matches_played, 3)

    def test_wins_and_losses_are_scoped_to_this_category_only(self):
        self._play_out_bracket(third_place=False)
        award_ranking_points(self.competition)

        other_category = RankingCategory.objects.create(name="Other")
        other_tournament = Tournament.objects.create(name="Other Open")
        other_competition = Competition.objects.create(
            tournament=other_tournament,
            name="Other Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            ranking_category=other_category,
        )
        champion = self.participants[0].individual_player
        Participant.objects.create(
            competition=other_competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=champion
        )

        rows_by_player = {row.player.pk: row for row in build_category_leaderboard(self.category)}
        self.assertEqual(rows_by_player[champion.pk].wins, 3)
        # Registering the same player in an unrelated category's competition
        # (with no matches at all) must not leak into this category's count.
        self.assertEqual(build_category_leaderboard(other_category), [])

    def test_player_with_only_elo_no_points_yet_still_appears(self):
        player = Player.objects.create(first_name="Solo", last_name="Elo", gender="M", mobile_number="09000009999")
        EloRating.objects.create(player=player, category=self.category, rating=1550.0, current_rank=1)

        rows = build_category_leaderboard(self.category)
        row = next(r for r in rows if r.player.pk == player.pk)
        self.assertEqual(row.points, 0)
        self.assertEqual(row.tournaments_played, 0)
        self.assertEqual(row.rating, 1550.0)

    def test_sorted_by_elo_rank_first(self):
        self._play_out_bracket(third_place=False)
        rows = build_category_leaderboard(self.category)
        ranked = [row for row in rows if row.elo_rank is not None]
        self.assertEqual(ranked, sorted(ranked, key=lambda r: r.elo_rank))
