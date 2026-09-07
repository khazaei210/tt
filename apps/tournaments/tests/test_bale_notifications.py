from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Group,
    Participant,
    ParticipantType,
    Stage,
    StageFormat,
    Tournament,
    TournamentStatus,
)

User = get_user_model()


class DrawGenerationNotifiesPlayersTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username="admin", password="pw", email="a@example.com")
        self.client.login(username="admin", password="pw")
        self.tournament = Tournament.objects.create(name="Open Cup", status=TournamentStatus.ONGOING)
        self.competition = Competition.objects.create(
            tournament=self.tournament, name="Singles", participant_type=ParticipantType.INDIVIDUAL
        )
        self.players = [
            Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900045{i:04d}")
            for i in range(4)
        ]
        self.participants = [
            Participant.objects.create(
                competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=player
            )
            for player in self.players
        ]

    def test_stage_bracket_generate_notifies_players(self):
        stage = Stage.objects.create(competition=self.competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        with patch("apps.tournaments.views.notify_matches_created") as mock_notify:
            mock_notify.return_value = [(self.players[0], "sent"), (self.players[1], "sent")]
            response = self.client.post(reverse("tournaments:stage_bracket_generate", kwargs={"pk": stage.pk}))
        mock_notify.assert_called_once()
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("via bale" in m.lower() for m in messages))

    def test_group_schedule_generate_notifies_players(self):
        stage = Stage.objects.create(competition=self.competition, name="Group Stage", stage_format=StageFormat.ROUND_ROBIN)
        group = Group.objects.create(stage=stage, name="Group A")
        for participant in self.participants:
            group.group_participants.create(participant=participant)
        with patch("apps.tournaments.views.notify_matches_created") as mock_notify:
            mock_notify.return_value = [(self.players[0], "sent")]
            response = self.client.post(reverse("tournaments:group_schedule_generate", kwargs={"pk": group.pk}))
        mock_notify.assert_called_once()
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("via bale" in m.lower() for m in messages))

    def test_failed_generation_does_not_notify(self):
        stage = Stage.objects.create(competition=self.competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        # Only one participant registered in a fresh competition -> NotEnoughParticipantsError.
        empty_competition = Competition.objects.create(
            tournament=self.tournament, name="Empty", participant_type=ParticipantType.INDIVIDUAL
        )
        empty_stage = Stage.objects.create(competition=empty_competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        with patch("apps.tournaments.views.notify_matches_created") as mock_notify:
            self.client.post(reverse("tournaments:stage_bracket_generate", kwargs={"pk": empty_stage.pk}))
        mock_notify.assert_not_called()

    def test_unexpected_notification_bug_does_not_break_bracket_generation(self):
        """A latent bug in the Bale notification path must not turn an
        already-successful bracket generation into a 500 — the bracket
        itself is still generated and the response still redirects."""
        stage = Stage.objects.create(competition=self.competition, name="Round 1", stage_format=StageFormat.KNOCKOUT)
        with patch("apps.tournaments.views.notify_matches_created", side_effect=RuntimeError("latent bug")):
            response = self.client.post(reverse("tournaments:stage_bracket_generate", kwargs={"pk": stage.pk}))
        self.assertRedirects(response, reverse("tournaments:stage_detail", kwargs={"pk": stage.pk}))
        self.assertTrue(stage.matches.exists())
