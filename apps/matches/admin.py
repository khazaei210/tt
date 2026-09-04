from django.contrib import admin

from .models import Match


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "competition", "group", "round_number", "status")
    list_filter = ("status", "competition")
    search_fields = ("participant_a__display_name", "participant_b__display_name")
