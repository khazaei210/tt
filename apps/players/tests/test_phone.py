from django.test import TestCase

from apps.players.phone import normalize_mobile_number


class NormalizeMobileNumberTests(TestCase):
    def test_local_format_unchanged(self):
        self.assertEqual(normalize_mobile_number("09123456789"), "09123456789")

    def test_strips_spaces_and_dashes(self):
        self.assertEqual(normalize_mobile_number("0912 345-6789"), "09123456789")

    def test_international_plus_prefix(self):
        self.assertEqual(normalize_mobile_number("+989123456789"), "09123456789")

    def test_international_00_prefix(self):
        self.assertEqual(normalize_mobile_number("00989123456789"), "09123456789")

    def test_bare_98_prefix(self):
        self.assertEqual(normalize_mobile_number("989123456789"), "09123456789")

    def test_blank_input(self):
        self.assertEqual(normalize_mobile_number(""), "")
        self.assertEqual(normalize_mobile_number(None), "")
