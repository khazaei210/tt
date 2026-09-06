import datetime

from django.test import SimpleTestCase

from apps.core.forms import JalaliDateField


class JalaliDateFieldTests(SimpleTestCase):
    def test_parses_jalali_string_to_gregorian_date(self):
        field = JalaliDateField(required=False)
        self.assertEqual(field.clean("1403/01/01"), datetime.date(2024, 3, 20))

    def test_accepts_dash_separator(self):
        field = JalaliDateField(required=False)
        self.assertEqual(field.clean("1403-01-01"), datetime.date(2024, 3, 20))

    def test_empty_value_is_none(self):
        field = JalaliDateField(required=False)
        self.assertIsNone(field.clean(""))

    def test_invalid_string_raises_validation_error(self):
        field = JalaliDateField(required=False)
        with self.assertRaises(Exception):
            field.clean("not-a-date")

    def test_invalid_calendar_date_raises_validation_error(self):
        field = JalaliDateField(required=False)
        with self.assertRaises(Exception):
            field.clean("1403/13/40")

    def test_prepare_value_formats_gregorian_date_as_jalali_string(self):
        field = JalaliDateField(required=False)
        self.assertEqual(field.prepare_value(datetime.date(2024, 3, 20)), "1403/01/01")

    def test_prepare_value_passes_through_existing_string(self):
        field = JalaliDateField(required=False)
        self.assertEqual(field.prepare_value("1403/01/01"), "1403/01/01")

    def test_round_trip(self):
        field = JalaliDateField(required=False)
        original = datetime.date(2026, 9, 6)
        jalali_string = field.prepare_value(original)
        self.assertEqual(field.clean(jalali_string), original)
