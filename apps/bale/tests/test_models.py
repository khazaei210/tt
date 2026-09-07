from django.test import TestCase, override_settings

from apps.bale.models import BaleSettings


class BaleSettingsTests(TestCase):
    def test_get_solo_creates_singleton_row(self):
        self.assertEqual(BaleSettings.objects.count(), 0)
        obj = BaleSettings.get_solo()
        self.assertEqual(obj.pk, 1)
        self.assertEqual(BaleSettings.objects.count(), 1)

    def test_get_solo_returns_same_row_on_repeated_calls(self):
        first = BaleSettings.get_solo()
        second = BaleSettings.get_solo()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BaleSettings.objects.count(), 1)

    @override_settings(BALE_BOT_TOKEN="env-token", BALE_BOT_USERNAME="env_bot")
    def test_effective_values_fall_back_to_settings_when_blank(self):
        obj = BaleSettings.get_solo()
        self.assertEqual(obj.effective_token, "env-token")
        self.assertEqual(obj.effective_username, "env_bot")

    @override_settings(BALE_BOT_TOKEN="env-token", BALE_BOT_USERNAME="env_bot")
    def test_effective_values_prefer_db_value_when_set(self):
        obj = BaleSettings.get_solo()
        obj.bot_token = "db-token"
        obj.bot_username = "db_bot"
        obj.save()
        self.assertEqual(obj.effective_token, "db-token")
        self.assertEqual(obj.effective_username, "db_bot")
