from django.test import TestCase

from apps.matches.models import Match
from apps.matches.services import record_set_score, record_walkover
from apps.players.models import DoublesPair, Player
from apps.rankings.elo import DEFAULT_ELO_RATING, expected_score, k_factor
from apps.rankings.models import EloRating, EloRatingEvent, RankingCategory
from apps.tournaments.models import (
    Competition,
    CompetitionRule,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
)


def make_player(name):
    return Player.objects.create(first_name=name, last_name="Test", gender="M")


class EloFormulaTests(TestCase):
    def test_expected_score_even_match_is_half(self):
        self.assertAlmostEqual(expected_score(1500, 1500), 0.5)

    def test_expected_score_favors_higher_rating(self):
        self.assertGreater(expected_score(1700, 1500), 0.5)
        self.assertLess(expected_score(1300, 1500), 0.5)

    def test_k_factor_is_higher_for_new_players(self):
        self.assertGreater(k_factor(1500, matches_played=5), k_factor(1500, matches_played=50))

    def test_k_factor_is_lower_for_high_rated_established_players(self):
        self.assertLess(k_factor(2450, matches_played=50), k_factor(1800, matches_played=50))


class EloMatchIntegrationTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Elo Open")
        self.category = RankingCategory.objects.create(name="Men's Singles Elo")
        self.competition = Competition.objects.create(
            tournament=self.tournament,
            name="Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            ranking_category=self.category,
        )
        CompetitionRule.objects.create(competition=self.competition, best_of_sets=5, points_per_set=11, win_by=2)
        self.stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        self.player_a = make_player("Alice")
        self.player_b = make_player("Bob")
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

    def _play_to_completion(self, match=None):
        match = match or self.match
        record_set_score(match, 1, 11, 5)
        record_set_score(match, 2, 11, 8)
        record_set_score(match, 3, 11, 9)

    def test_completed_match_creates_ratings_for_both_players_starting_from_default(self):
        self._play_to_completion()
        rating_a = EloRating.objects.get(player=self.player_a, category=self.category)
        rating_b = EloRating.objects.get(player=self.player_b, category=self.category)
        self.assertGreater(rating_a.rating, DEFAULT_ELO_RATING)
        self.assertLess(rating_b.rating, DEFAULT_ELO_RATING)
        self.assertEqual(rating_a.matches_played, 1)
        self.assertEqual(rating_b.matches_played, 1)

    def test_even_match_gains_and_losses_are_symmetric(self):
        self._play_to_completion()
        rating_a = EloRating.objects.get(player=self.player_a, category=self.category)
        rating_b = EloRating.objects.get(player=self.player_b, category=self.category)
        self.assertAlmostEqual(
            rating_a.rating - DEFAULT_ELO_RATING, DEFAULT_ELO_RATING - rating_b.rating, places=6
        )

    def test_underdog_win_yields_bigger_swing_than_favorite_win(self):
        EloRating.objects.create(player=self.player_a, category=self.category, rating=1200, matches_played=40)
        EloRating.objects.create(player=self.player_b, category=self.category, rating=1800, matches_played=40)
        self._play_to_completion()  # participant_a (the underdog) wins
        event_a = EloRatingEvent.objects.get(player=self.player_a, match=self.match)
        self.assertGreater(event_a.delta, 20)  # a big upset gain, not a routine ~half-K gain

    def test_creates_audit_events_for_both_players(self):
        self._play_to_completion()
        self.assertEqual(EloRatingEvent.objects.filter(match=self.match).count(), 2)
        winner_event = EloRatingEvent.objects.get(player=self.player_a, match=self.match)
        loser_event = EloRatingEvent.objects.get(player=self.player_b, match=self.match)
        self.assertTrue(winner_event.won)
        self.assertFalse(loser_event.won)
        self.assertEqual(winner_event.opponent_participant, self.participant_b)

    def test_ranks_are_computed_across_the_category(self):
        self._play_to_completion()
        rating_a = EloRating.objects.get(player=self.player_a, category=self.category)
        rating_b = EloRating.objects.get(player=self.player_b, category=self.category)
        self.assertEqual(rating_a.current_rank, 1)
        self.assertEqual(rating_b.current_rank, 2)

    def test_walkover_does_not_affect_rating(self):
        record_walkover(self.match, self.participant_a.id)
        self.assertFalse(EloRating.objects.filter(category=self.category).exists())

    def test_no_ranking_category_leaves_match_unrated(self):
        self.competition.ranking_category = None
        self.competition.save(update_fields=["ranking_category"])
        self._play_to_completion()
        self.assertFalse(EloRating.objects.filter(category=self.category).exists())

    def test_correcting_the_winner_reverses_and_reapplies_the_rating_change(self):
        self._play_to_completion()
        rating_a_after_first = EloRating.objects.get(player=self.player_a, category=self.category).rating
        self.assertGreater(rating_a_after_first, DEFAULT_ELO_RATING)

        # Correct the result the other way.
        record_set_score(self.match, 1, 5, 11, allow_correction=True)
        record_set_score(self.match, 2, 8, 11, allow_correction=True)
        record_set_score(self.match, 3, 9, 11, allow_correction=True)

        rating_a_after_correction = EloRating.objects.get(player=self.player_a, category=self.category).rating
        rating_b_after_correction = EloRating.objects.get(player=self.player_b, category=self.category).rating
        self.assertLess(rating_a_after_correction, DEFAULT_ELO_RATING)
        self.assertGreater(rating_b_after_correction, DEFAULT_ELO_RATING)
        # Only one event per player should remain — the reversal removed the stale one.
        self.assertEqual(EloRatingEvent.objects.filter(match=self.match, player=self.player_a).count(), 1)
        self.assertEqual(
            EloRating.objects.get(player=self.player_a, category=self.category).matches_played, 1
        )

    def test_doubles_participants_both_get_rated_off_the_pair_average(self):
        player_c = make_player("Carol")
        player_d = make_player("Dave")
        pair_ab = DoublesPair.objects.create(player_one=self.player_a, player_two=player_c)
        pair_cd = DoublesPair.objects.create(player_one=self.player_b, player_two=player_d)
        doubles_competition = Competition.objects.create(
            tournament=self.tournament,
            name="Doubles",
            participant_type=ParticipantType.DOUBLES,
            ranking_category=self.category,
        )
        CompetitionRule.objects.create(competition=doubles_competition, best_of_sets=5, points_per_set=11, win_by=2)
        doubles_stage = Stage.objects.create(
            competition=doubles_competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
        participant_ab = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair_ab
        )
        participant_cd = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair_cd
        )
        doubles_match = Match.objects.create(
            competition=doubles_competition,
            stage=doubles_stage,
            round_number=1,
            participant_a=participant_ab,
            participant_b=participant_cd,
        )
        self._play_to_completion(doubles_match)

        rating_alice = EloRating.objects.get(player=self.player_a, category=self.category).rating
        rating_carol = EloRating.objects.get(player=player_c, category=self.category).rating
        self.assertAlmostEqual(rating_alice, rating_carol, places=6)
        self.assertGreater(rating_alice, DEFAULT_ELO_RATING)


class EloTeamParticipantTestCase(TestCase):
    def test_team_matches_are_skipped_no_individual_players_to_credit(self):
        from apps.teams.models import Team

        tournament = Tournament.objects.create(name="Team Open")
        category = RankingCategory.objects.create(name="Team Elo")
        competition = Competition.objects.create(
            tournament=tournament, name="Teams", participant_type=ParticipantType.TEAM, ranking_category=category
        )
        CompetitionRule.objects.create(competition=competition, best_of_sets=5, points_per_set=11, win_by=2)
        stage = Stage.objects.create(competition=competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        team_a = Team.objects.create(name="Team A")
        team_b = Team.objects.create(name="Team B")
        participant_a = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.TEAM, team=team_a
        )
        participant_b = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.TEAM, team=team_b
        )
        match = Match.objects.create(
            competition=competition, stage=stage, round_number=1, participant_a=participant_a, participant_b=participant_b
        )
        record_set_score(match, 1, 11, 5)
        record_set_score(match, 2, 11, 8)
        record_set_score(match, 3, 11, 9)

        self.assertFalse(EloRating.objects.filter(category=category).exists())
