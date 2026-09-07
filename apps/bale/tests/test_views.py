from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.bale.models import BaleSettings

User = get_user_model()


class BaleSettingsViewTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username="root", password="pw", email="root@example.com")
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("bale:settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_plain_staff_user_forbidden(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("bale:settings"))
        self.assertEqual(response.status_code, 403)

    def test_plain_user_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("bale:settings"))
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view(self):
        self.client.login(username="root", password="pw")
        response = self.client.get(reverse("bale:settings"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_save_settings(self):
        self.client.login(username="root", password="pw")
        response = self.client.post(
            reverse("bale:settings"), {"bot_token": "new-token", "bot_username": "NewBot"}
        )
        self.assertRedirects(response, reverse("bale:settings"))
        obj = BaleSettings.get_solo()
        self.assertEqual(obj.bot_token, "new-token")
        self.assertEqual(obj.bot_username, "NewBot")

    def test_blank_submission_clears_db_override(self):
        obj = BaleSettings.get_solo()
        obj.bot_token = "old-token"
        obj.save()
        self.client.login(username="root", password="pw")
        self.client.post(reverse("bale:settings"), {"bot_token": "", "bot_username": ""})
        obj.refresh_from_db()
        self.assertEqual(obj.bot_token, "")

    def test_nav_link_visible_only_to_superuser(self):
        self.client.login(username="root", password="pw")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Bale settings")

        self.client.logout()
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Bale settings")
