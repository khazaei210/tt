"""Jalali (Persian) calendar entry for Gregorian-backed Django DateFields.

The domain (models, services, standings, rankings) stores and computes
with plain Gregorian `datetime.date` values throughout — only *entry and
display* of dates in forms is Jalali. `JalaliDateField` converts between
the two at the form boundary, via jdatetime, so nothing downstream needs
to know the widget exists. Pair it with `JalaliDateWidget`, which is a
plain text input driven by the vendored jalalidatepicker JS
(static/vendor/jalalidatepicker.min.js, wired up in templates/base.html).
"""

import re

import jdatetime
from django import forms

JALALI_DATE_RE = re.compile(r"^(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})$")


class JalaliDateWidget(forms.TextInput):
    """Text input that jalalidatepicker attaches to via `data-jdp`.

    On focus it shows a Jalali calendar and writes a "YYYY/MM/DD" Jalali
    string back into the input's value; see
    `jalaliDatepicker.startWatch()` in templates/base.html.
    """

    def __init__(self, attrs=None):
        default_attrs = {
            "data-jdp": "",
            "autocomplete": "off",
            "dir": "ltr",
            "placeholder": "YYYY/MM/DD",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class JalaliDateField(forms.DateField):
    """A DateField whose text representation is a Jalali "YYYY/MM/DD"
    string. `clean()` still returns a plain Gregorian `date`, so the rest
    of the app (model instance, services) never sees a Jalali value."""

    widget = JalaliDateWidget

    def to_python(self, value):
        if value in self.empty_values:
            return None
        match = JALALI_DATE_RE.match(str(value).strip())
        if not match:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        jy, jm, jd = (int(part) for part in match.groups())
        try:
            return jdatetime.date(jy, jm, jd).togregorian()
        except ValueError:
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")

    def prepare_value(self, value):
        if hasattr(value, "year") and not isinstance(value, str):
            return jdatetime.date.fromgregorian(date=value).strftime("%Y/%m/%d")
        return value
