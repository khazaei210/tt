from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.models import Match, MatchStatus
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    StaffRole,
    Tournament,
    TournamentStaff,
)

User = get_user_model()


class MatchScoringViewTestCase(TestCase):
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
        self.plain_user = User.objects.create_user(username="plain", password="pw")
        self.scorekeeper = User.objects.create_user(username="scorekeeper", password="pw")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.scorekeeper, role=StaffRole.SCOREKEEPER
        )


class StartMatchViewTests(MatchScoringViewTestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse("matches:start", args=[self.match.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_plain_user_forbidden(self):
        self.client.login(username="plain", password="pw")
        response = self.client.post(reverse("matches:start", args=[self.match.pk]))
        self.assertEqual(response.status_code, 403)

    def test_scorekeeper_can_start_match(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.post(reverse("matches:start", args=[self.match.pk]))
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.LIVE)

    def test_htmx_request_returns_scoreboard_partial(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.post(reverse("matches:start", args=[self.match.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="scoreboard"')
        self.assertNotContains(response, "<html")


class SpecialResultViewTests(MatchScoringViewTestCase):
    def test_walkover_requires_winner_choice(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.post(reverse("matches:walkover", args=[self.match.pk]), {})
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.SCHEDULED)

    def test_walkover_with_winner_completes_match(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.post(
            reverse("matches:walkover", args=[self.match.pk]), {"winner": "a"}
        )
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, MatchStatus.WALKOVER)
        self.assertEqual(self.match.winner_id, self.participant_a.id)

    def test_plain_user_forbidden_from_recording_default(self):
        self.client.login(username="plain", password="pw")
        response = self.client.post(reverse("matches:default", args=[self.match.pk]), {"winner": "a"})
        self.assertEqual(response.status_code, 403)


class ClaimMatchViewTests(MatchScoringViewTestCase):
    def test_scorekeeper_can_claim_as_referee(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.post(
            reverse("matches:claim", args=[self.match.pk]), {"role": "referee"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.referee_id, self.scorekeeper.id)


class ScorerDashboardViewTests(MatchScoringViewTestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("matches:scorer_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_no_role_sees_empty_state(self):
        self.client.login(username="plain", password="pw")
        response = self.client.get(reverse("matches:scorer_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["dashboard"].has_scoring_role)

    def test_assigned_match_appears_in_pending_list(self):
        self.match.scorekeeper = self.scorekeeper
        self.match.save(update_fields=["scorekeeper"])
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.get(reverse("matches:scorer_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.match, response.context["dashboard"].pending_matches)

    def test_unassigned_match_appears_in_pickup_list(self):
        self.client.login(username="scorekeeper", password="pw")
        response = self.client.get(reverse("matches:scorer_dashboard"))
        self.assertIn(self.match, response.context["dashboard"].unassigned_matches)

    def test_live_match_gets_a_score_summary(self):
        from apps.matches.models import MatchSet

        self.match.scorekeeper = self.scorekeeper
        self.match.status = MatchStatus.LIVE
        self.match.save(update_fields=["scorekeeper", "status"])
        MatchSet.objects.create(match=self.match, set_number=1, participant_a_score=11, participant_b_score=9)

        self.client.login(username="scorekeeper", password="pw")
        response = self.client.get(reverse("matches:scorer_dashboard"))
        live = response.context["dashboard"].live_matches[0]
        self.assertEqual(live.live_score_summary.sets_score, "1-0")
        self.assertEqual(live.live_score_summary.last_set_score, "11-9")
