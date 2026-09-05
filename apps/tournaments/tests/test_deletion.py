from django.contrib.auth import get_user_model
from django.db.models import RestrictedError
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


class TournamentDeletionTestCase(TestCase):
    """Deleting a Tournament (or a Competition within one) must cascade
    cleanly through Stage/Match/Participant even when a match has already
    been decided (has a winner) — regression coverage for a bug where
    Match.participant_a/b/winner used on_delete=PROTECT, which
    unconditionally blocks deletion of the referenced Participant even
    when the referencing Match rows are being deleted in the same cascade.
    on_delete=RESTRICT allows that cascade while still blocking a
    standalone Participant delete.
    """

    def setUp(self):
        self.tournament = Tournament.objects.create(name="Deletable Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.stage = Stage.objects.create(
            competition=self.competition, name="Groups", stage_format=StageFormat.ROUND_ROBIN
        )
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
            winner=self.participant_a,
            status=MatchStatus.COMPLETED,
        )


class DeletionCascadeTests(TournamentDeletionTestCase):
    def test_deleting_tournament_with_a_decided_match_succeeds(self):
        self.tournament.delete()
        self.assertFalse(Tournament.objects.filter(pk=self.tournament.pk).exists())
        self.assertFalse(Match.objects.filter(pk=self.match.pk).exists())

    def test_deleting_tournament_does_not_delete_the_players(self):
        self.tournament.delete()
        self.assertTrue(Player.objects.filter(pk=self.player_a.pk).exists())
        self.assertTrue(Player.objects.filter(pk=self.player_b.pk).exists())

    def test_deleting_competition_with_a_decided_match_succeeds(self):
        self.competition.delete()
        self.assertFalse(Competition.objects.filter(pk=self.competition.pk).exists())
        self.assertFalse(Match.objects.filter(pk=self.match.pk).exists())

    def test_standalone_participant_delete_is_still_restricted(self):
        with self.assertRaises(RestrictedError):
            self.participant_a.delete()


class DeletionViewTests(TournamentDeletionTestCase):
    def setUp(self):
        super().setUp()
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(
            tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER
        )

    def test_tournament_delete_view_succeeds_with_a_decided_match(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(reverse("tournaments:delete", args=[self.tournament.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Tournament.objects.filter(pk=self.tournament.pk).exists())

    def test_competition_delete_view_succeeds_with_a_decided_match(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(reverse("tournaments:competition_delete", args=[self.competition.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Competition.objects.filter(pk=self.competition.pk).exists())
