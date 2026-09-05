"""Shared CSV export helper (CLAUDE.md section 20: "Export reports").

Kept in core rather than duplicated per app: every export in this project
is small (one tournament's matches, one group's standings, one ranking
category) — never a background/streamed job — so a single in-memory
HttpResponse is the right level of complexity, not a generic export
framework.
"""

import csv

from django.http import HttpResponse


def csv_response(filename, header, rows):
    """Build a CSV file download from a header row and an iterable of rows.

    Writes a UTF-8 BOM first — without it, Excel guesses the wrong
    encoding for non-ASCII text (e.g. Persian player names) and shows
    mojibake instead of respecting the UTF-8 content.
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response
