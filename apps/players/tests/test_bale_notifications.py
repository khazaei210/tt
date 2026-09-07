from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player

User = get_user_model()


class PlayerResetPasswordBaleNotificationTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.player_user = User.objects.create_user(username="playeruser", password="old-pw")
        self.player = Player.objects.create(first_name="A", last_name="Test", gender="M", user=self.player_user)
        self.client.login(username="staffuser", password="pw")

    def test_notify_checkbox_off_does_not_call_bale(self):
        with patch("apps.players.views.send_password_reset_notification") as mock_notify:
            self.client.post(reverse("players:reset_password", kwargs={"pk": self.player.pk}))
        mock_notify.assert_not_called()

    def test_notify_checkbox_on_with_linked_chat_sends_message(self):
        self.player.bale_chat_id = 123
        self.player.save(update_fields=["bale_chat_id"])
        with patch("apps.players.views.send_password_reset_notification", return_value="sent") as mock_notify:
            response = self.client.post(
                reverse("players:reset_password", kwargs={"pk": self.player.pk}), {"notify_via_bale": "on"}
            )
        mock_notify.assert_called_once()
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("also sent" in m.lower() or "via bale" in m.lower() for m in messages))

    def test_notify_checkbox_on_without_linked_chat_warns(self):
        with patch("apps.players.views.send_password_reset_notification", return_value="not_linked"):
            response = self.client.post(
                reverse("players:reset_password", kwargs={"pk": self.player.pk}), {"notify_via_bale": "on"}
            )
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("hasn't linked" in m for m in messages))

    def test_notify_checkbox_on_with_failed_delivery_warns(self):
        with patch("apps.players.views.send_password_reset_notification", return_value="failed"):
            response = self.client.post(
                reverse("players:reset_password", kwargs={"pk": self.player.pk}), {"notify_via_bale": "on"}
            )
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("failed" in m.lower() for m in messages))
