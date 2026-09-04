from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player

User = get_user_model()


class PlayerPermissionTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(first_name="A", last_name="Test", gender="M")
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_anonymous_redirected_to_login_on_add(self):
        response = self.client.get(reverse("players:add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_plain_authenticated_user_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("players:add"))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_add(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("players:add"))
        self.assertEqual(response.status_code, 200)

    def test_plain_user_cannot_delete(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("players:delete", kwargs={"pk": self.player.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Player.objects.filter(pk=self.player.pk).exists())

    def test_staff_user_can_delete(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("players:delete", kwargs={"pk": self.player.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Player.objects.filter(pk=self.player.pk).exists())

    def test_anonymous_can_view_player_list(self):
        response = self.client.get(reverse("players:list"))
        self.assertEqual(response.status_code, 200)
