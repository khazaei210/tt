from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.players.models import Player
from apps.rankings.elo import DEFAULT_ELO_RATING
from apps.rankings.models import EloRating
from apps.rankings.services import get_default_ranking_category

User = get_user_model()


class PlayerRegistrationTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(username="staffuser", password="pw", is_staff=True)
        self.client.login(username="staffuser", password="pw")

    def _valid_data(self, **overrides):
        data = {
            "first_name": "New",
            "last_name": "Player",
            "gender": "M",
            "club": "",
            "country": "",
            "mobile_number": "0912 111 2222",
            "is_active": "on",
            "username": "",
        }
        data.update(overrides)
        return data

    def test_registering_a_player_creates_a_login_together(self):
        response = self.client.post(reverse("players:add"), self._valid_data())
        player = Player.objects.get(first_name="New", last_name="Player")
        self.assertIsNotNone(player.user)
        self.assertRedirects(response, reverse("players:edit", kwargs={"pk": player.pk}))

    def test_mobile_number_is_normalized_and_required(self):
        self.client.post(reverse("players:add"), self._valid_data())
        player = Player.objects.get(first_name="New", last_name="Player")
        self.assertEqual(player.mobile_number, "09121112222")

    def test_blank_mobile_number_is_rejected_with_no_player_created(self):
        response = self.client.post(reverse("players:add"), self._valid_data(mobile_number=""))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Player.objects.filter(first_name="New", last_name="Player").exists())

    def test_duplicate_mobile_number_is_rejected(self):
        Player.objects.create(first_name="Existing", last_name="Player", gender="M", mobile_number="09121112222")
        response = self.client.post(reverse("players:add"), self._valid_data())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Player.objects.filter(mobile_number="09121112222").count(), 1)

    def test_explicit_username_is_used(self):
        self.client.post(reverse("players:add"), self._valid_data(username="customname"))
        player = Player.objects.get(first_name="New", last_name="Player")
        self.assertEqual(player.user.username, "customname")

    def test_blank_username_is_auto_suggested_from_name(self):
        self.client.post(reverse("players:add"), self._valid_data())
        player = Player.objects.get(first_name="New", last_name="Player")
        self.assertEqual(player.user.username, "newplayer")

    def test_success_message_shows_generated_password(self):
        response = self.client.post(reverse("players:add"), self._valid_data(), follow=True)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("password" in m.lower() for m in messages))

    def test_registration_creates_a_default_elo_rating(self):
        self.client.post(reverse("players:add"), self._valid_data())
        player = Player.objects.get(first_name="New", last_name="Player")
        rating = EloRating.objects.get(player=player, category=get_default_ranking_category())
        self.assertEqual(rating.rating, DEFAULT_ELO_RATING)
        self.assertEqual(rating.matches_played, 0)
