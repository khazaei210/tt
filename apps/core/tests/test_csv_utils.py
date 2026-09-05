from django.test import SimpleTestCase

from apps.core.csv_utils import csv_response


class CsvResponseTests(SimpleTestCase):
    def test_sets_csv_content_type_and_attachment_filename(self):
        response = csv_response("report.csv", ["A", "B"], [[1, 2]])
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="report.csv"')

    def test_writes_header_and_rows_with_a_leading_bom(self):
        response = csv_response("report.csv", ["Name", "Score"], [["Ali", 11], ["Sara", 9]])
        raw = response.content
        self.assertTrue(raw.startswith("﻿".encode("utf-8")))
        decoded = raw.decode("utf-8-sig")
        self.assertIn("Name,Score", decoded)
        self.assertIn("Ali,11", decoded)
        self.assertIn("Sara,9", decoded)

    def test_non_ascii_text_round_trips(self):
        response = csv_response("report.csv", ["Name"], [["علی"]])
        decoded = response.content.decode("utf-8-sig")
        self.assertIn("علی", decoded)
