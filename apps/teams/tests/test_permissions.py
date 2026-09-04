from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.teams.models import Team

User = get_user_model()


class TeamPermissionTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Test Club")
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.plain_user = User.objects.create_user(username="plainuser", password="pw")

    def test_anonymous_redirected_to_login_on_add(self):
        response = self.client.get(reverse("teams:add"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_plain_authenticated_user_forbidden(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.get(reverse("teams:add"))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_add(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.get(reverse("teams:add"))
        self.assertEqual(response.status_code, 200)

    def test_plain_user_cannot_delete(self):
        self.client.login(username="plainuser", password="pw")
        response = self.client.post(reverse("teams:delete", kwargs={"pk": self.team.pk}))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_staff_user_can_delete(self):
        self.client.login(username="staffuser", password="pw")
        response = self.client.post(reverse("teams:delete", kwargs={"pk": self.team.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())

    def test_anonymous_can_view_team_detail(self):
        response = self.client.get(reverse("teams:detail", kwargs={"pk": self.team.pk}))
        self.assertEqual(response.status_code, 200)
