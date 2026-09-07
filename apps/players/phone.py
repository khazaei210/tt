"""Normalizes a mobile number to a canonical local Iranian format
("09XXXXXXXXX") regardless of whether it was typed by staff (e.g.
"0912 345 6789") or came from a Bale-shared Contact (e.g. "+989123456789",
"00989123456789"). Both sides of the match in apps.bale.services must
go through this so a player only ever needs to type their number once.
"""

import re


def normalize_mobile_number(raw):
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) > 10:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits
