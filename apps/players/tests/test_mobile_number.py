from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.players.models import Player


class PlayerMobileNumberTests(TestCase):
    def test_save_normalizes_mobile_number(self):
        player = Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="+98 912 345 6789")
        self.assertEqual(player.mobile_number, "09123456789")

    def test_blank_mobile_number_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="")

    def test_duplicate_mobile_number_is_rejected(self):
        Player.objects.create(first_name="A", last_name="Test", gender="M", mobile_number="09123456789")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Player.objects.create(first_name="B", last_name="Other", gender="M", mobile_number="09123456789")
