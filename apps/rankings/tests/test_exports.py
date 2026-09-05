from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.rankings.models import PlayerRanking, RankingCategory


class RankingCategoryCsvTests(TestCase):
    def setUp(self):
        self.category = RankingCategory.objects.create(name="Men's Singles CSV")
        player = Player.objects.create(first_name="Ranked", last_name="Player", gender="M")
        PlayerRanking.objects.create(player=player, category=self.category, points=100, current_rank=1)

    def test_category_csv_is_public_and_contains_player_name(self):
        response = self.client.get(reverse("rankings:category_csv", args=[self.category.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8-sig")
        self.assertIn("Ranked Player", content)
        self.assertIn("100", content)
