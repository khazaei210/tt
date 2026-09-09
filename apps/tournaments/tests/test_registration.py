from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.matches.services import generate_stage_bracket
from apps.players.models import Player
from apps.tournaments.models import (
    Competition,
    Participant,
    ParticipantType,
    StaffRole,
    Stage,
    StageFormat,
    Tournament,
    TournamentAuditLog,
    TournamentStaff,
)
from apps.tournaments.services.registration import (
    AlreadyRegisteredError,
    CannotWithdrawError,
    CompetitionFullError,
    NoPlayerProfileError,
    NotRegisteredError,
    RegistrationClosedError,
    UnsupportedParticipantTypeError,
    register_self,
    unregister_self,
)

User = get_user_model()


class RegistrationServiceTestCase(TestCase):
    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament,
            name="Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            registration_open=True,
        )
        self.user = User.objects.create_user(username="alice", password="pw")
        self.player = Player.objects.create(
            user=self.user, first_name="Alice", last_name="A", gender="F", mobile_number="09000000001"
        )


class RegisterSelfTests(RegistrationServiceTestCase):
    def test_registers_the_users_own_player(self):
        participant = register_self(self.competition, self.user)
        self.assertEqual(participant.individual_player_id, self.player.id)
        self.assertEqual(self.competition.participants.count(), 1)

    def test_logs_an_audit_entry(self):
        register_self(self.competition, self.user)
        self.assertTrue(
            TournamentAuditLog.objects.filter(tournament=self.tournament, actor=self.user).exists()
        )

    def test_raises_when_registration_is_closed(self):
        self.competition.registration_open = False
        self.competition.save(update_fields=["registration_open"])
        with self.assertRaises(RegistrationClosedError):
            register_self(self.competition, self.user)

    def test_raises_when_already_registered(self):
        register_self(self.competition, self.user)
        with self.assertRaises(AlreadyRegisteredError):
            register_self(self.competition, self.user)

    def test_raises_when_full(self):
        self.competition.registration_capacity = 1
        self.competition.save(update_fields=["registration_capacity"])
        other = User.objects.create_user(username="bob", password="pw")
        Player.objects.create(user=other, first_name="Bob", last_name="B", gender="M", mobile_number="09000000002")
        register_self(self.competition, other)
        with self.assertRaises(CompetitionFullError):
            register_self(self.competition, self.user)

    def test_raises_without_a_player_profile(self):
        bare_user = User.objects.create_user(username="nobody", password="pw")
        with self.assertRaises(NoPlayerProfileError):
            register_self(self.competition, bare_user)

    def test_raises_for_a_non_individual_competition(self):
        doubles_competition = Competition.objects.create(
            tournament=self.tournament, name="Doubles", participant_type=ParticipantType.DOUBLES, registration_open=True
        )
        with self.assertRaises(UnsupportedParticipantTypeError):
            register_self(doubles_competition, self.user)


class UnregisterSelfTests(RegistrationServiceTestCase):
    def test_withdraws_an_existing_registration(self):
        register_self(self.competition, self.user)
        unregister_self(self.competition, self.user)
        self.assertEqual(self.competition.participants.count(), 0)

    def test_logs_an_audit_entry(self):
        register_self(self.competition, self.user)
        unregister_self(self.competition, self.user)
        self.assertTrue(
            TournamentAuditLog.objects.filter(tournament=self.tournament, action="unregistered").exists()
        )

    def test_raises_when_not_registered(self):
        with self.assertRaises(NotRegisteredError):
            unregister_self(self.competition, self.user)

    def test_raises_once_the_draw_includes_the_participant(self):
        register_self(self.competition, self.user)
        other_user = User.objects.create_user(username="carol", password="pw")
        Player.objects.create(user=other_user, first_name="Carol", last_name="C", gender="F", mobile_number="09000000003")
        register_self(self.competition, other_user)

        stage = Stage.objects.create(competition=self.competition, name="Bracket", stage_format=StageFormat.KNOCKOUT)
        generate_stage_bracket(stage, seeded=False)

        with self.assertRaises(CannotWithdrawError):
            unregister_self(self.competition, self.user)


class CompetitionRegisterViewTests(RegistrationServiceTestCase):
    def test_requires_login(self):
        response = self.client.post(reverse("tournaments:competition_register", kwargs={"pk": self.competition.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.competition.participants.count(), 0)

    def test_logged_in_user_can_register(self):
        self.client.login(username="alice", password="pw")
        response = self.client.post(
            reverse("tournaments:competition_register", kwargs={"pk": self.competition.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.competition.participants.count(), 1)

    def test_error_when_registration_closed_does_not_create_a_participant(self):
        self.competition.registration_open = False
        self.competition.save(update_fields=["registration_open"])
        self.client.login(username="alice", password="pw")
        self.client.post(reverse("tournaments:competition_register", kwargs={"pk": self.competition.pk}))
        self.assertEqual(self.competition.participants.count(), 0)


class CompetitionUnregisterViewTests(RegistrationServiceTestCase):
    def test_withdraws_the_current_users_registration(self):
        register_self(self.competition, self.user)
        self.client.login(username="alice", password="pw")
        response = self.client.post(
            reverse("tournaments:competition_unregister", kwargs={"pk": self.competition.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.competition.participants.count(), 0)

    def test_cannot_withdraw_someone_elses_registration(self):
        register_self(self.competition, self.user)
        other_user = User.objects.create_user(username="dave", password="pw")
        self.client.login(username="dave", password="pw")
        self.client.post(reverse("tournaments:competition_unregister", kwargs={"pk": self.competition.pk}))
        self.assertEqual(self.competition.participants.count(), 1)


class StaffAddCapacityTests(TestCase):
    """Capacity is enforced for staff-added participants too, not just self-registration."""

    def setUp(self):
        self.tournament = Tournament.objects.create(name="Open")
        self.competition = Competition.objects.create(
            tournament=self.tournament,
            name="Singles",
            participant_type=ParticipantType.INDIVIDUAL,
            registration_capacity=1,
        )
        self.manager = User.objects.create_user(username="manager", password="pw")
        TournamentStaff.objects.create(tournament=self.tournament, user=self.manager, role=StaffRole.TOURNAMENT_MANAGER)
        self.players = [
            Player.objects.create(first_name=f"P{i}", last_name="Test", gender="M", mobile_number=f"0900001{i:04d}")
            for i in range(2)
        ]

    def test_staff_can_add_while_registration_is_closed(self):
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:participant_add", kwargs={"competition_pk": self.competition.pk}),
            {"individual_player": self.players[0].pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.competition.participants.count(), 1)

    def test_staff_add_is_blocked_once_capacity_is_reached(self):
        Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.players[0]
        )
        self.client.login(username="manager", password="pw")
        response = self.client.post(
            reverse("tournaments:participant_add", kwargs={"competition_pk": self.competition.pk}),
            {"individual_player": self.players[1].pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.competition.participants.count(), 1)

    def test_staff_add_logs_an_audit_entry(self):
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse("tournaments:participant_add", kwargs={"competition_pk": self.competition.pk}),
            {"individual_player": self.players[0].pk},
        )
        self.assertTrue(
            TournamentAuditLog.objects.filter(tournament=self.tournament, action="participant_added_by_staff").exists()
        )

    def test_staff_remove_logs_an_audit_entry(self):
        participant = Participant.objects.create(
            competition=self.competition, participant_type=ParticipantType.INDIVIDUAL, individual_player=self.players[0]
        )
        self.client.login(username="manager", password="pw")
        self.client.post(
            reverse(
                "tournaments:participant_delete", kwargs={"competition_pk": self.competition.pk, "pk": participant.pk}
            )
        )
        self.assertTrue(
            TournamentAuditLog.objects.filter(
                tournament=self.tournament, action="participant_removed_by_staff"
            ).exists()
        )
