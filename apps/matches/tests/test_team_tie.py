from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.models import Match, MatchStatus, TieLineup
from apps.matches.services import (
    compute_group_standings,
    generate_group_schedule,
    generate_stage_bracket,
    record_set_score,
)
from apps.matches.team_tie import (
    ORDER_OF_PLAY,
    InvalidLineupError,
    LineupMissingError,
    TieAlreadyGeneratedError,
    generate_tie_matches,
    set_lineup,
    summarize_tie,
)
from apps.players.models import Player
from apps.rankings.elo import ensure_default_elo_rating
from apps.rankings.models import EloRating
from apps.teams.models import Team, TeamMembership
from apps.tournaments.models import (
    Competition,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    StaffRole,
    Tournament,
    TournamentStaff,
)

User = get_user_model()


def _make_team(name, player_prefix, mobile_prefix, size=3):
    team = Team.objects.create(name=name)
    players = []
    for i in range(size):
        player = Player.objects.create(
            first_name=f"{player_prefix}{i}", last_name="Test", gender="M", mobile_number=f"{mobile_prefix}{i:03d}"
        )
        TeamMembership.objects.create(team=team, player=player, is_active=True)
        players.append(player)
    return team, players


class TeamTieTestCase(TestCase):
    """Shared fixture: a Team competition with two 3-player teams entered
    as Participants in one round-robin group."""

    def setUp(self):
        self.tournament = Tournament.objects.create(name="Team Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Men's Team", participant_type=ParticipantType.TEAM
        )
        self.team_a, self.players_a = _make_team("Alpha", "A", "0910000")
        self.team_b, self.players_b = _make_team("Bravo", "B", "0920000")
        self.participant_a = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.TEAM, team=self.team_a
        )
        self.participant_b = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.TEAM, team=self.team_b
        )

    def _make_tie(self):
        stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        group = Group.objects.create(stage=stage, name="A")
        GroupParticipant.objects.create(group=group, participant=self.participant_a)
        GroupParticipant.objects.create(group=group, participant=self.participant_b)
        generate_group_schedule(group)
        tie = group.matches.get()
        # generate_group_schedule doesn't guarantee side order, but our
        # tests rely on tie.participant_a/b == team_a/b for readability.
        if tie.participant_a_id != self.participant_a.id:
            tie.participant_a, tie.participant_b = tie.participant_b, tie.participant_a
            tie.save(update_fields=["participant_a", "participant_b"])
        return tie, group

    def _set_both_lineups(self, tie):
        set_lineup(tie, self.team_a, self.players_a)
        set_lineup(tie, self.team_b, self.players_b)

    def _play_sub_match(self, sub_match, *, a_wins):
        scores = (11, 5) if a_wins else (5, 11)
        for set_number in (1, 2, 3):
            record_set_score(sub_match, set_number, *scores)


class SetLineupTests(TeamTieTestCase):
    def test_rejects_a_player_not_on_the_roster(self):
        tie, _group = self._make_tie()
        outsider = Player.objects.create(first_name="Out", last_name="Sider", gender="M", mobile_number="09999999999")
        with self.assertRaises(InvalidLineupError):
            set_lineup(tie, self.team_a, [self.players_a[0], self.players_a[1], outsider])

    def test_rejects_duplicate_players(self):
        tie, _group = self._make_tie()
        with self.assertRaises(InvalidLineupError):
            set_lineup(tie, self.team_a, [self.players_a[0], self.players_a[0], self.players_a[1]])

    def test_rejects_a_team_not_in_this_tie(self):
        tie, _group = self._make_tie()
        other_team, other_players = _make_team("Charlie", "C", "0930000")
        with self.assertRaises(InvalidLineupError):
            set_lineup(tie, other_team, other_players)

    def test_saved_lineup_is_retrievable(self):
        tie, _group = self._make_tie()
        set_lineup(tie, self.team_a, self.players_a)
        lineup = TieLineup.objects.get(tie=tie, team=self.team_a)
        self.assertEqual(lineup.players(), self.players_a)


class GenerateTieMatchesTests(TeamTieTestCase):
    def test_requires_both_lineups(self):
        tie, _group = self._make_tie()
        set_lineup(tie, self.team_a, self.players_a)
        with self.assertRaises(LineupMissingError):
            generate_tie_matches(tie)

    def test_creates_five_sub_matches_in_ittf_order(self):
        tie, _group = self._make_tie()
        self._set_both_lineups(tie)
        sub_matches = generate_tie_matches(tie)
        self.assertEqual(len(sub_matches), 5)

        for order, (sub, (i, j)) in enumerate(zip(sub_matches, ORDER_OF_PLAY), start=1):
            self.assertEqual(sub.tie_order, order)
            self.assertEqual(sub.parent_tie_id, tie.id)
            self.assertEqual(sub.participant_a.individual_player_id, self.players_a[i].id)
            self.assertEqual(sub.participant_b.individual_player_id, self.players_b[j].id)
            self.assertTrue(sub.participant_a.is_tie_slot)
            self.assertTrue(sub.participant_b.is_tie_slot)
            self.assertEqual(sub.competition_id, self.competition.id)
            self.assertEqual(sub.stage_id, tie.stage_id)
            self.assertEqual(sub.group_id, tie.group_id)

    def test_raises_if_already_generated(self):
        tie, _group = self._make_tie()
        self._set_both_lineups(tie)
        generate_tie_matches(tie)
        with self.assertRaises(TieAlreadyGeneratedError):
            generate_tie_matches(tie)

    def test_same_player_reuses_one_tie_slot_participant_across_ties(self):
        """A player nominated in two different ties within the same
        competition gets one shared shadow Participant, not two."""
        tie1, group = self._make_tie()
        self._set_both_lineups(tie1)
        generate_tie_matches(tie1)

        # A rematch (double round robin) in the same group/competition.
        second = Match.objects.create(
            competition=self.competition, stage=tie1.stage, group=group, round_number=2,
            participant_a=self.participant_a, participant_b=self.participant_b,
        )
        set_lineup(second, self.team_a, self.players_a)
        set_lineup(second, self.team_b, self.players_b)
        generate_tie_matches(second)

        self.assertEqual(
            Participant.objects.filter(
                competition=self.competition, is_tie_slot=True, individual_player=self.players_a[0]
            ).count(),
            1,
        )


class RefreshTieResultTests(TeamTieTestCase):
    def _generated_tie(self):
        tie, group = self._make_tie()
        self._set_both_lineups(tie)
        generate_tie_matches(tie)
        tie.refresh_from_db()
        return tie, group

    def test_tie_undecided_before_three_wins(self):
        tie, _group = self._generated_tie()
        subs = list(tie.tie_sub_matches.order_by("tie_order"))
        self._play_sub_match(subs[0], a_wins=True)
        self._play_sub_match(subs[1], a_wins=False)
        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.SCHEDULED)
        self.assertIsNone(tie.winner_id)

    def test_tie_decided_at_three_one(self):
        tie, _group = self._generated_tie()
        subs = list(tie.tie_sub_matches.order_by("tie_order"))
        for sub, a_wins in zip(subs, [True, False, True, True]):
            self._play_sub_match(sub, a_wins=a_wins)
        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.COMPLETED)
        self.assertEqual(tie.winner_id, self.participant_a.id)
        summary = summarize_tie(tie)
        self.assertEqual((summary.wins_a, summary.wins_b), (3, 1))

    def test_dead_rubber_can_still_be_played_without_changing_the_winner(self):
        tie, _group = self._generated_tie()
        subs = list(tie.tie_sub_matches.order_by("tie_order"))
        for sub in subs[:3]:
            self._play_sub_match(sub, a_wins=True)
        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.COMPLETED)
        self.assertEqual(tie.winner_id, self.participant_a.id)

        # The 4th match (a dead rubber) is still playable, and team B
        # winning it doesn't reopen or flip the tie's decided result.
        self._play_sub_match(subs[3], a_wins=False)
        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.COMPLETED)
        self.assertEqual(tie.winner_id, self.participant_a.id)

    def test_team_b_can_win(self):
        tie, _group = self._generated_tie()
        subs = list(tie.tie_sub_matches.order_by("tie_order"))
        for sub in subs[:3]:
            self._play_sub_match(sub, a_wins=False)
        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.COMPLETED)
        self.assertEqual(tie.winner_id, self.participant_b.id)


class EloIntegrationTests(TeamTieTestCase):
    def test_elo_updates_for_sub_match_players_not_the_tie_itself(self):
        for player in self.players_a + self.players_b:
            ensure_default_elo_rating(player)
        category = self.competition.ranking_category
        rating_before = EloRating.objects.get(player=self.players_a[0], category=category).rating

        tie, _group = self._make_tie()
        self._set_both_lineups(tie)
        generate_tie_matches(tie)
        sub = tie.tie_sub_matches.get(tie_order=1)  # A vs X
        self.assertEqual(sub.participant_a.individual_player_id, self.players_a[0].id)
        self._play_sub_match(sub, a_wins=True)

        rating_after = EloRating.objects.get(player=self.players_a[0], category=category).rating
        self.assertGreater(rating_after, rating_before)

        # The tie match itself is never Elo-rated: sync_elo_ratings skips
        # Team participants (apps.rankings.services.players_for_participant
        # returns [] for a Team), so it created no EloRatingEvent for it.
        from apps.rankings.models import EloRatingEvent

        self.assertFalse(EloRatingEvent.objects.filter(match=tie).exists())
        self.assertTrue(EloRatingEvent.objects.filter(match=sub).exists())


class KnockoutProgressionTests(TeamTieTestCase):
    def test_tie_winner_propagates_like_an_ordinary_match(self):
        stage = Stage.objects.create(competition=self.competition, name="Knockout", stage_format=StageFormat.KNOCKOUT)
        generate_stage_bracket(stage, seeded=False, participant_ids=[self.participant_a.id, self.participant_b.id])
        tie = stage.matches.get()

        self._set_both_lineups(tie)
        generate_tie_matches(tie)
        subs = list(tie.tie_sub_matches.order_by("tie_order"))
        for sub in subs[:3]:
            self._play_sub_match(sub, a_wins=True)

        tie.refresh_from_db()
        self.assertEqual(tie.status, MatchStatus.COMPLETED)
        self.assertEqual(tie.winner_id, self.participant_a.id)


class TeamStandingsTests(TeamTieTestCase):
    def test_individual_match_ratio_breaks_a_match_points_tie(self):
        """Three teams, each winning one tie and losing one (all 2 match
        points), broken by individual-match win ratio — ITTF §3.7.5.2."""
        team_c, players_c = _make_team("Charlie", "C", "0930000")
        participant_c = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.TEAM, team=team_c
        )
        stage = Stage.objects.create(competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN)
        group = Group.objects.create(stage=stage, name="A")
        for p in (self.participant_a, self.participant_b, participant_c):
            GroupParticipant.objects.create(group=group, participant=p)
        generate_group_schedule(group)

        def play_tie(p1, players1, p2, players2, wins_p1, wins_p2):
            tie = Match.objects.get(group=group, participant_a__in=[p1, p2], participant_b__in=[p1, p2])
            if tie.participant_a_id != p1.id:
                tie.participant_a, tie.participant_b = tie.participant_b, tie.participant_a
                tie.save(update_fields=["participant_a", "participant_b"])
            set_lineup(tie, p1.team, players1)
            set_lineup(tie, p2.team, players2)
            generate_tie_matches(tie)
            subs = list(tie.tie_sub_matches.order_by("tie_order"))
            outcomes = [True] * wins_p1 + [False] * wins_p2
            for sub, a_wins in zip(subs, outcomes):
                self._play_sub_match(sub, a_wins=a_wins)

        # A beats B 3-0, B beats C 3-0, C beats A 3-1: a 3-way cycle, all
        # three teams 1 win/1 loss (2 match points) — match points and
        # head-to-head alone can't resolve it. Individual-match
        # difference does: A +3-2=+1, B -3+3=0, C -3+2=-1, all distinct.
        play_tie(self.participant_a, self.players_a, self.participant_b, self.players_b, 3, 0)
        play_tie(self.participant_b, self.players_b, participant_c, players_c, 3, 0)
        play_tie(participant_c, players_c, self.participant_a, self.players_a, 3, 1)

        rows = compute_group_standings(group)
        self.assertEqual(len(rows), 3)
        by_participant = {row["participant"].id: row for row in rows}
        for participant in (self.participant_a, self.participant_b, participant_c):
            self.assertEqual(by_participant[participant.id]["wins"], 1)
            self.assertEqual(by_participant[participant.id]["losses"], 1)

        # Ranked strictly by individual-match difference: A (+1) > B (0) > C (-1).
        rank_by_participant = {pid: row["rank"] for pid, row in by_participant.items()}
        self.assertEqual(rank_by_participant[self.participant_a.id], 1)
        self.assertEqual(rank_by_participant[self.participant_b.id], 2)
        self.assertEqual(rank_by_participant[participant_c.id], 3)
        self.assertEqual(
            by_participant[self.participant_a.id]["individual_matches_won"]
            - by_participant[self.participant_a.id]["individual_matches_lost"],
            1,
        )


class TieDetailViewTests(TeamTieTestCase):
    """End-to-end through the actual views: view the tie page, submit
    both lineups, generate matches, score one to a decision — the same
    flow a tournament manager drives from the browser."""

    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER
        )
        self.tie, self.group = self._make_tie()
        self.client.login(username="manager", password="pw")

    def test_tie_detail_uses_tie_template_and_shows_lineup_forms(self):
        response = self.client.get(reverse("matches:detail", args=[self.tie.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "matches/tie_detail.html")
        self.assertContains(response, self.team_a.name)
        self.assertContains(response, self.team_b.name)

    def test_submitting_both_lineups_then_generating_matches(self):
        for side, players in (("a", self.players_a), ("b", self.players_b)):
            response = self.client.post(
                reverse("matches:tie_lineup_save", args=[self.tie.pk, side]),
                {
                    f"{side}-player_a": players[0].pk,
                    f"{side}-player_b": players[1].pk,
                    f"{side}-player_c": players[2].pk,
                },
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual(TieLineup.objects.filter(tie=self.tie).count(), 2)

        response = self.client.post(reverse("matches:tie_matches_generate", args=[self.tie.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.tie.tie_sub_matches.count(), 5)

        # The generated sub-matches score through the ordinary,
        # unmodified per-match scoring view.
        first_sub = self.tie.tie_sub_matches.order_by("tie_order").first()
        for set_number, (a, b) in enumerate([(11, 5), (11, 5), (11, 5)], start=1):
            response = self.client.post(
                reverse("matches:set_save", args=[first_sub.pk]),
                {"set_number": set_number, "participant_a_score": a, "participant_b_score": b},
            )
            self.assertEqual(response.status_code, 302)
        first_sub.refresh_from_db()
        self.assertEqual(first_sub.status, MatchStatus.COMPLETED)

    def test_lineup_rejects_a_non_roster_player(self):
        outsider = Player.objects.create(first_name="Out", last_name="Sider", gender="M", mobile_number="09999999998")
        response = self.client.post(
            reverse("matches:tie_lineup_save", args=[self.tie.pk, "a"]),
            {
                "a-player_a": outsider.pk,
                "a-player_b": self.players_a[1].pk,
                "a-player_c": self.players_a[2].pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TieLineup.objects.filter(tie=self.tie, team=self.team_a).exists())
