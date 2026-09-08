from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.rankings.models import PlayerRanking
from apps.rankings.services import get_default_ranking_category

User = get_user_model()


class HomeViewTests(TestCase):
    def test_anonymous_visitor_sees_the_overall_ranking_table(self):
        category = get_default_ranking_category()
        player = Player.objects.create(
            first_name="Ranked", last_name="Player", gender="M", mobile_number="09000000099"
        )
        PlayerRanking.objects.create(player=player, category=category, points=42, current_rank=1)

        response = self.client.get(reverse("core:home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")
        self.assertContains(response, "Ranked Player")
        self.assertContains(response, reverse("reports:player_statistics", args=[player.pk]))

    def test_player_only_account_is_redirected_to_player_dashboard(self):
        user = User.objects.create_user(username="playeruser", password="pw")
        Player.objects.create(first_name="A", last_name="Test", gender="M", user=user, mobile_number="09000000098")
        self.client.login(username="playeruser", password="pw")

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("players:dashboard"))

    def test_staff_account_is_redirected_to_manager_dashboard(self):
        User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.client.login(username="staffuser", password="pw")

        response = self.client.get(reverse("core:home"))

        self.assertRedirects(response, reverse("tournaments:manager_dashboard"))
