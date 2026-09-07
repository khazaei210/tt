from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player

User = get_user_model()


class AccountListPermissionTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("accounts:list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_plain_authenticated_user_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("accounts:list"))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_view(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("accounts:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staffuser")
        self.assertContains(response, "plainuser")

    def test_search_filters_by_username(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("accounts:list"), {"q": "plain"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "plainuser")
        self.assertNotContains(response, "staffuser")


class AccountRegisterTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.superuser = User.objects.create_superuser(username="root", password="pw", email="root@example.com")
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_anonymous_cannot_register(self):
        response = self.client.post(reverse("accounts:register"), {"username": "newref"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)
        self.assertFalse(User.objects.filter(username="newref").exists())

    def test_plain_user_cannot_register(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("accounts:register"), {"username": "newref"})
        self.assertEqual(response.status_code, 403)

    def test_staff_can_register_a_plain_account(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:register"), {"username": "newref"})
        self.assertRedirects(response, reverse("accounts:list"))
        user = User.objects.get(username="newref")
        self.assertFalse(user.is_staff)
        self.assertTrue(user.has_usable_password())

    def test_staff_cannot_grant_staff_access_on_registration(self):
        self.client.login(username="staffuser", password="pw")
        self.client.post(reverse("accounts:register"), {"username": "newref", "is_staff": "on"})
        user = User.objects.get(username="newref")
        self.assertFalse(user.is_staff)

    def test_superuser_can_register_a_staff_account(self):
        self.client.login(username="root", password="pw")
        self.client.post(reverse("accounts:register"), {"username": "newstaff", "is_staff": "on"})
        user = User.objects.get(username="newstaff")
        self.assertTrue(user.is_staff)

    def test_duplicate_username_is_rejected(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:register"), {"username": "plainuser"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="plainuser").count(), 1)

    def test_blank_username_is_rejected(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:register"), {"username": "  "})
        self.assertEqual(response.status_code, 200)


class AccountResetPasswordTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="old-pw")

    def test_staff_can_reset_any_accounts_password(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:reset_password", kwargs={"pk": self.plain_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.assertFalse(self.client.login(username="plainuser", password="old-pw"))

    def test_plain_user_cannot_reset_password(self):
        self.client.login(username="plainuser", password="old-pw")
        response = self.client.post(reverse("accounts:reset_password", kwargs={"pk": self.staff_user.pk}))
        self.assertEqual(response.status_code, 403)

    def test_get_not_allowed(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("accounts:reset_password", kwargs={"pk": self.plain_user.pk}))
        self.assertEqual(response.status_code, 405)


class AccountResetPasswordBaleNotificationTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.player_user = User.objects.create_user(username="playeruser", password="pw")
        self.player = Player.objects.create(first_name="A", last_name="Test", gender="M", user=self.player_user)
        self.client.login(username="staffuser", password="pw")

    def test_notify_checkbox_ignored_without_player_profile(self):
        plain_user = User.objects.create_user(username="noplayeruser", password="pw")
        with patch("apps.accounts.views.send_password_reset_notification") as mock_notify:
            self.client.post(reverse("accounts:reset_password", kwargs={"pk": plain_user.pk}), {"notify_via_bale": "on"})
        mock_notify.assert_not_called()

    def test_notify_checkbox_on_with_linked_chat_sends_message(self):
        self.player.bale_chat_id = 123
        self.player.save(update_fields=["bale_chat_id"])
        with patch("apps.accounts.views.send_password_reset_notification", return_value="sent") as mock_notify:
            self.client.post(
                reverse("accounts:reset_password", kwargs={"pk": self.player_user.pk}), {"notify_via_bale": "on"}
            )
        mock_notify.assert_called_once()


class AccountToggleActiveTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_staff_can_deactivate_another_account(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:toggle_active", kwargs={"pk": self.plain_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.plain_user.refresh_from_db()
        self.assertFalse(self.plain_user.is_active)

    def test_deactivated_account_cannot_log_in(self):
        self.client.login(username="staffuser", password="pw")
        self.client.post(reverse("accounts:toggle_active", kwargs={"pk": self.plain_user.pk}))
        self.client.logout()
        self.assertFalse(self.client.login(username="plainuser", password="pw"))

    def test_staff_cannot_deactivate_self(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:toggle_active", kwargs={"pk": self.staff_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.is_active)

    def test_toggle_is_reversible(self):
        self.client.login(username="staffuser", password="pw")
        url = reverse("accounts:toggle_active", kwargs={"pk": self.plain_user.pk})
        self.client.post(url)
        self.client.post(url)
        self.plain_user.refresh_from_db()
        self.assertTrue(self.plain_user.is_active)


class AccountToggleStaffTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(username="root", password="pw", email="root@example.com")
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_superuser_can_grant_staff(self):
        self.client.login(username="root", password="pw")
        response = self.client.post(reverse("accounts:toggle_staff", kwargs={"pk": self.plain_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.plain_user.refresh_from_db()
        self.assertTrue(self.plain_user.is_staff)

    def test_superuser_can_revoke_staff(self):
        self.client.login(username="root", password="pw")
        response = self.client.post(reverse("accounts:toggle_staff", kwargs={"pk": self.staff_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_staff)

    def test_plain_staff_user_cannot_toggle_staff_access(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:toggle_staff", kwargs={"pk": self.plain_user.pk}))
        self.assertEqual(response.status_code, 403)

    def test_superuser_cannot_toggle_own_staff_access(self):
        self.client.login(username="root", password="pw")
        response = self.client.post(reverse("accounts:toggle_staff", kwargs={"pk": self.superuser.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_staff)


class AccountDeleteTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_staff_can_delete_another_account(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:delete", kwargs={"pk": self.plain_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.assertFalse(User.objects.filter(pk=self.plain_user.pk).exists())

    def test_staff_cannot_delete_self(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("accounts:delete", kwargs={"pk": self.staff_user.pk}))
        self.assertRedirects(response, reverse("accounts:list"))
        self.assertTrue(User.objects.filter(pk=self.staff_user.pk).exists())

    def test_deleting_account_unlinks_but_keeps_player(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", user=self.plain_user)
        self.client.login(username="staffuser", password="pw")
        self.client.post(reverse("accounts:delete", kwargs={"pk": self.plain_user.pk}))
        player.refresh_from_db()
        self.assertIsNone(player.user_id)


class LoginRedirectTests(TestCase):
    def test_player_only_account_redirects_to_player_dashboard(self):
        user = User.objects.create_user(username="playeruser", password="pw")
        Player.objects.create(first_name="A", last_name="Test", gender="M", user=user)
        response = self.client.post(reverse("accounts:login"), {"username": "playeruser", "password": "pw"})
        self.assertRedirects(response, reverse("players:dashboard"))

    def test_staff_account_redirects_to_home(self):
        User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        response = self.client.post(reverse("accounts:login"), {"username": "staffuser", "password": "pw"})
        self.assertRedirects(response, reverse("core:home"))

    def test_account_with_no_player_profile_redirects_to_home(self):
        User.objects.create_user(username="plainuser", password="pw")
        response = self.client.post(reverse("accounts:login"), {"username": "plainuser", "password": "pw"})
        self.assertRedirects(response, reverse("core:home"))

    def test_explicit_next_param_takes_priority_over_player_redirect(self):
        user = User.objects.create_user(username="playeruser", password="pw")
        Player.objects.create(first_name="A", last_name="Test", gender="M", user=user)
        login_url = f"{reverse('accounts:login')}?next={reverse('rankings:category_list')}"
        response = self.client.post(login_url, {"username": "playeruser", "password": "pw"})
        self.assertRedirects(response, reverse("rankings:category_list"))
