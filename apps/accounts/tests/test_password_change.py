from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

User = get_user_model()


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.plain_user = User.objects.create_user(username="plainuser", password="old-pw-123")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_any_authenticated_user_can_view_the_form(self):
        self.client.login(username="plainuser", password="old-pw-123")
        response = self.client.get(reverse("accounts:password_change"))
        self.assertEqual(response.status_code, 200)

    def test_changing_own_password_works_and_keeps_session(self):
        self.client.login(username="plainuser", password="old-pw-123")
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "old-pw-123",
                "new_password1": "brand-new-pw-456",
                "new_password2": "brand-new-pw-456",
            },
        )
        self.assertRedirects(response, reverse("accounts:password_change"))
        # update_session_auth_hash kept this request's session valid —
        # a follow-up request as the same client is still authenticated.
        response = self.client.get(reverse("players:dashboard"))
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        self.assertFalse(self.client.login(username="plainuser", password="old-pw-123"))
        self.assertTrue(self.client.login(username="plainuser", password="brand-new-pw-456"))

    def test_wrong_current_password_is_rejected(self):
        self.client.login(username="plainuser", password="old-pw-123")
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "wrong-password",
                "new_password1": "brand-new-pw-456",
                "new_password2": "brand-new-pw-456",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.login(username="plainuser", password="old-pw-123"))

    def test_mismatched_new_passwords_are_rejected(self):
        self.client.login(username="plainuser", password="old-pw-123")
        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "old-pw-123",
                "new_password1": "brand-new-pw-456",
                "new_password2": "something-else-789",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.client.login(username="plainuser", password="old-pw-123"))

    def test_nav_link_visible_to_any_authenticated_user(self):
        self.client.login(username="plainuser", password="old-pw-123")
        # "Change password" already has a Django-shipped Persian
        # translation, so pin English explicitly rather than rely on
        # settings.LANGUAGE_CODE ("fa") — this checks the link renders at
        # all, not which language it renders in. The request itself must
        # stay inside the override too: LocaleMiddleware activates "en"
        # process-wide for the /en/-prefixed URL and doesn't revert it
        # afterward, which would otherwise leak into later tests in the
        # same run (translation.override restores the prior language on
        # exit regardless of what happened inside).
        # core:home redirects any authenticated user to their dashboard,
        # so it can't be used as the generic "some page with the nav"
        # target here — password_change renders 200 for every
        # authenticated user regardless of role, same as home used to.
        with translation.override("en"):
            response = self.client.get(reverse("accounts:password_change"))
        self.assertContains(response, "Change password")
