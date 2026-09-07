from unittest.mock import patch

from django.test import TestCase

from apps.bale.client import BaleAPIError
from apps.bale.exceptions import BaleNotLinkedError
from apps.bale.services import (
    handle_update,
    notify_matches_created,
    notify_player,
    password_reset_message,
    send_password_reset_notification,
)
from apps.matches.models import Match, MatchStatus
from apps.players.models import DoublesPair, Player
from apps.teams.models import Team, TeamMembership
from apps.tournaments.models import Competition, Participant, ParticipantType, Stage, StageFormat, Tournament, TournamentStatus


def _make_tournament_bits():
    tournament = Tournament.objects.create(name="Open Cup", status=TournamentStatus.ONGOING)
    competition = Competition.objects.create(
        tournament=tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
    )
    stage = Stage.objects.create(competition=competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
    return tournament, competition, stage


class NotifyPlayerTests(TestCase):
    def test_raises_when_not_linked(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="09000000031")
        with self.assertRaises(BaleNotLinkedError):
            notify_player(player, "hello")

    def test_sends_to_linked_chat(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=555, mobile_number="09000000030")
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            notify_player(player, "hello")
        mock_client_cls.return_value.call.assert_called_once_with("sendMessage", chat_id=555, text="hello")


class NotifyMatchesCreatedTests(TestCase):
    def setUp(self):
        self.tournament, self.competition, self.stage = _make_tournament_bits()

    def test_individual_match_notifies_both_linked_players(self):
        player_a = Player.objects.create(first_name="A", last_name="One", gender="M", bale_chat_id=1, mobile_number="09000000029")
        player_b = Player.objects.create(first_name="B", last_name="Two", gender="M", bale_chat_id=2, mobile_number="09000000028")
        pa = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_a
        )
        pb = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_b
        )
        match = Match.objects.create(
            competition=self.competition, stage=self.stage, round_number=1, participant_a=pa, participant_b=pb
        )
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(status == "sent" for _player, status in results))
        self.assertEqual(mock_client_cls.return_value.call.call_count, 2)

    def test_unlinked_player_reported_not_linked(self):
        player_a = Player.objects.create(first_name="A", last_name="One", gender="M", mobile_number="09000000027")
        player_b = Player.objects.create(first_name="B", last_name="Two", gender="M", bale_chat_id=2, mobile_number="09000000026")
        pa = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_a
        )
        pb = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_b
        )
        match = Match.objects.create(
            competition=self.competition, stage=self.stage, round_number=1, participant_a=pa, participant_b=pb
        )
        with patch("apps.bale.services.BaleClient"):
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        statuses = dict((player.pk, status) for player, status in results)
        self.assertEqual(statuses[player_a.pk], "not_linked")
        self.assertEqual(statuses[player_b.pk], "sent")

    def test_doubles_match_notifies_both_pair_members(self):
        p1 = Player.objects.create(first_name="A", last_name="One", gender="M", bale_chat_id=1, mobile_number="09000000025")
        p2 = Player.objects.create(first_name="B", last_name="Two", gender="M", bale_chat_id=2, mobile_number="09000000024")
        p3 = Player.objects.create(first_name="C", last_name="Three", gender="M", bale_chat_id=3, mobile_number="09000000023")
        p4 = Player.objects.create(first_name="D", last_name="Four", gender="M", bale_chat_id=4, mobile_number="09000000022")
        pair1 = DoublesPair.objects.create(player_one=p1, player_two=p2)
        pair2 = DoublesPair.objects.create(player_one=p3, player_two=p4)
        doubles_competition = Competition.objects.create(
            tournament=self.tournament, name="Doubles", participant_type=ParticipantType.DOUBLES
        )
        stage = Stage.objects.create(competition=doubles_competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        pa = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair1
        )
        pb = Participant.objects.create(
            competition=doubles_competition, participant_type=ParticipantType.DOUBLES, doubles_pair=pair2
        )
        match = Match.objects.create(competition=doubles_competition, stage=stage, round_number=1, participant_a=pa, participant_b=pb)
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        self.assertEqual(len(results), 4)
        self.assertEqual(mock_client_cls.return_value.call.call_count, 4)

    def test_team_match_notifies_active_roster_only(self):
        active = Player.objects.create(first_name="A", last_name="One", gender="M", bale_chat_id=1, mobile_number="09000000021")
        inactive = Player.objects.create(first_name="B", last_name="Two", gender="M", bale_chat_id=2, mobile_number="09000000020")
        team_a = Team.objects.create(name="Team A")
        team_b = Team.objects.create(name="Team B")
        TeamMembership.objects.create(team=team_a, player=active, is_active=True)
        TeamMembership.objects.create(team=team_a, player=inactive, is_active=False)
        team_competition = Competition.objects.create(
            tournament=self.tournament, name="Teams", participant_type=ParticipantType.TEAM
        )
        stage = Stage.objects.create(competition=team_competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        pa = Participant.objects.create(competition=team_competition, participant_type=ParticipantType.TEAM, team=team_a)
        pb = Participant.objects.create(competition=team_competition, participant_type=ParticipantType.TEAM, team=team_b)
        match = Match.objects.create(competition=team_competition, stage=stage, round_number=1, participant_a=pa, participant_b=pb)
        with patch("apps.bale.services.BaleClient"):
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        notified_players = {player.pk for player, _status in results}
        self.assertIn(active.pk, notified_players)
        self.assertNotIn(inactive.pk, notified_players)

    def test_bye_match_is_skipped(self):
        player_a = Player.objects.create(first_name="A", last_name="One", gender="M", bale_chat_id=1, mobile_number="09000000019")
        pa = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_a
        )
        bye = Participant.objects.create(competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, is_bye=True)
        match = Match.objects.create(
            competition=self.competition,
            stage=self.stage,
            round_number=1,
            participant_a=pa,
            participant_b=bye,
            is_bye=True,
        )
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        self.assertEqual(results, [])
        mock_client_cls.return_value.call.assert_not_called()

    def test_api_failure_is_reported_not_raised(self):
        player_a = Player.objects.create(first_name="A", last_name="One", gender="M", bale_chat_id=1, mobile_number="09000000018")
        player_b = Player.objects.create(first_name="B", last_name="Two", gender="M", bale_chat_id=2, mobile_number="09000000017")
        pa = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_a
        )
        pb = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player_b
        )
        match = Match.objects.create(
            competition=self.competition, stage=self.stage, round_number=1, participant_a=pa, participant_b=pb
        )
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            mock_client_cls.return_value.call.side_effect = BaleAPIError("boom")
            results = notify_matches_created(Match.objects.filter(pk=match.pk))
        self.assertEqual(len(results), 2)
        self.assertTrue(all(status == "boom" for _player, status in results))


class HandleUpdateTests(TestCase):
    def test_start_sends_link_prompt_with_keyboard(self):
        update = {"message": {"chat": {"id": 42}, "text": "/start"}}
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update(update)
        args, kwargs = mock_client_cls.return_value.call.call_args
        self.assertEqual(args[0], "sendMessage")
        self.assertEqual(kwargs["chat_id"], 42)
        self.assertIn("reply_markup", kwargs)

    def test_contact_links_matching_player(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="09123456789")
        update = {"message": {"chat": {"id": 99}, "contact": {"phone_number": "+989123456789"}}}
        with patch("apps.bale.services.BaleClient"):
            handle_update(update)
        player.refresh_from_db()
        self.assertEqual(player.bale_chat_id, 99)

    def test_contact_with_no_matching_player_sends_not_found(self):
        update = {"message": {"chat": {"id": 99}, "contact": {"phone_number": "+989120000000"}}}
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update(update)
        mock_client_cls.return_value.call.assert_called_once()
        self.assertEqual(Player.objects.filter(bale_chat_id=99).count(), 0)

    def test_unrelated_message_is_ignored(self):
        update = {"message": {"chat": {"id": 99}, "text": "hello there"}}
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update(update)
        mock_client_cls.return_value.call.assert_not_called()

    def test_update_without_message_is_ignored(self):
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update({"callback_query": {}})
        mock_client_cls.return_value.call.assert_not_called()


class NextGamesCommandTests(TestCase):
    def _send(self, chat_id, text):
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update({"message": {"chat": {"id": chat_id}, "text": text}})
        return mock_client_cls.return_value.call

    def test_unlinked_chat_is_told_to_link_first(self):
        call = self._send(1, "next_games")
        call.assert_called_once()
        self.assertIn("start", call.call_args.kwargs["text"].lower())

    def test_leading_slash_is_accepted(self):
        Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=2, mobile_number="09000000070")
        call = self._send(2, "/next_games")
        call.assert_called_once()

    def test_linked_with_no_upcoming_matches(self):
        Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=3, mobile_number="09000000071")
        call = self._send(3, "next_games")
        call.assert_called_once()
        self.assertIn("no upcoming", call.call_args.kwargs["text"].lower())

    def test_linked_with_an_upcoming_match(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=4, mobile_number="09000000072")
        opponent = Player.objects.create(first_name="B", last_name="Rival", gender="M", mobile_number="09000000073")
        tournament, competition, stage = _make_tournament_bits()
        pa = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
        )
        pb = Participant.objects.create(
            competition=competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=opponent
        )
        Match.objects.create(
            competition=competition, stage=stage, round_number=1, participant_a=pa, participant_b=pb,
            status=MatchStatus.SCHEDULED,
        )
        call = self._send(4, "next_games")
        call.assert_called_once()
        text = call.call_args.kwargs["text"]
        self.assertIn("Open Cup", text)
        self.assertIn("Singles", text)


class MyRankCommandTests(TestCase):
    def _send(self, chat_id, text):
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            handle_update({"message": {"chat": {"id": chat_id}, "text": text}})
        return mock_client_cls.return_value.call

    def test_unlinked_chat_is_told_to_link_first(self):
        call = self._send(10, "my_rank")
        call.assert_called_once()
        self.assertIn("start", call.call_args.kwargs["text"].lower())

    def test_linked_with_no_ranking_yet(self):
        Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=11, mobile_number="09000000080")
        call = self._send(11, "my_rank")
        call.assert_called_once()
        self.assertIn("no ranking", call.call_args.kwargs["text"].lower())

    def test_linked_with_elo_and_points(self):
        from apps.rankings.models import EloRating, PlayerRanking, RankingCategory

        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=12, mobile_number="09000000081")
        category = RankingCategory.objects.create(name="Men's Singles")
        EloRating.objects.create(player=player, category=category, rating=1620.0, current_rank=2)
        PlayerRanking.objects.create(player=player, category=category, points=80, current_rank=3)

        call = self._send(12, "my_rank")
        call.assert_called_once()
        text = call.call_args.kwargs["text"]
        self.assertIn("Men's Singles", text)
        self.assertIn("1620", text)
        self.assertIn("80", text)


class PasswordResetMessageTests(TestCase):
    def test_contains_username_and_password(self):
        text = password_reset_message("alice", "s3cret")
        self.assertIn("alice", text)
        self.assertIn("s3cret", text)


class SendPasswordResetNotificationTests(TestCase):
    def test_returns_sent_and_calls_bale_when_linked(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=1, mobile_number="09000000016")
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            status = send_password_reset_notification(player, "alice", "s3cret")
        self.assertEqual(status, "sent")
        mock_client_cls.return_value.call.assert_called_once()

    def test_returns_not_linked_without_raising(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="09000000015")
        status = send_password_reset_notification(player, "alice", "s3cret")
        self.assertEqual(status, "not_linked")

    def test_returns_failed_on_api_error_without_raising(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=1, mobile_number="09000000014")
        with patch("apps.bale.services.BaleClient") as mock_client_cls:
            mock_client_cls.return_value.call.side_effect = BaleAPIError("boom")
            status = send_password_reset_notification(player, "alice", "s3cret")
        self.assertEqual(status, "failed")

    def test_returns_failed_on_unexpected_exception_without_raising(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", bale_chat_id=1, mobile_number="09000000013")
        with patch("apps.bale.services.notify_player", side_effect=RuntimeError("latent bug")):
            status = send_password_reset_notification(player, "alice", "s3cret")
        self.assertEqual(status, "failed")
