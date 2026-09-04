from django.contrib import admin

from .models import Match, MatchSet


class MatchSetInline(admin.TabularInline):
    model = MatchSet
    extra = 0


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "competition", "group", "round_number", "status", "winner")
    list_filter = ("status", "competition")
    search_fields = ("participant_a__display_name", "participant_b__display_name")
    inlines = [MatchSetInline]
