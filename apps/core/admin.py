"""Shared Django admin base classes.

Every app's admin.py should subclass ModelAdmin/TabularInline/StackedInline
from here instead of django.contrib.admin's, to get two things uniformly:

- The Unfold theme (unfold.admin.*).
- Locale-aware date fields: a Jalali (Persian) picker when the admin is
  viewed in Persian, Django's normal Gregorian admin date widget otherwise.
  Scoped to the admin only — the site's own forms (apps/core/forms.py) are
  a separate, always-Jalali widget by deliberate choice, untouched here.
"""

from django.db import models
from django.utils.translation import get_language
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.admin import StackedInline as UnfoldStackedInline
from unfold.admin import TabularInline as UnfoldTabularInline

from .forms import JalaliDateField, JalaliDateWidget


class AdminJalaliDateWidget(JalaliDateWidget):
    """Same jalalidatepicker text input as the site's own JalaliDateWidget,
    plus its JS/CSS as widget Media — the admin doesn't load
    templates/base.html, which is what wires those up everywhere else."""

    class Media:
        css = {"all": ("vendor/jalalidatepicker.min.css",)}
        js = ("vendor/jalalidatepicker.min.js", "admin/js/jalali_admin_init.js")


class AdminJalaliDateField(JalaliDateField):
    widget = AdminJalaliDateWidget


class LocaleAwareDateAdminMixin:
    """Swaps plain DateField (not DateTimeField — models.DateTimeField is a
    subclass of models.DateField, and datetime fields like Match.start_time
    aren't in scope here) form fields to the Jalali picker only while the
    admin is being viewed in Persian."""

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        is_plain_date = isinstance(db_field, models.DateField) and not isinstance(db_field, models.DateTimeField)
        if is_plain_date and get_language() == "fa":
            # Both are needed: ModelAdmin.formfield_for_dbfield's own
            # defaults (django.contrib.admin.options.FORMFIELD_FOR_DBFIELD_DEFAULTS)
            # already inject widget=AdminDateWidget for every DateField ahead
            # of these kwargs; only overriding form_class leaves that
            # explicit widget in place (a field's own `widget` class
            # attribute loses to an explicit widget= constructor kwarg).
            kwargs.setdefault("form_class", AdminJalaliDateField)
            kwargs.setdefault("widget", AdminJalaliDateWidget)
        return super().formfield_for_dbfield(db_field, request, **kwargs)


class ModelAdmin(LocaleAwareDateAdminMixin, UnfoldModelAdmin):
    pass


class TabularInline(LocaleAwareDateAdminMixin, UnfoldTabularInline):
    pass


class StackedInline(LocaleAwareDateAdminMixin, UnfoldStackedInline):
    pass
