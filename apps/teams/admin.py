from django.contrib import admin

from apps.core.admin import ModelAdmin, TabularInline

from .models import Team, TeamMembership


class TeamMembershipInline(TabularInline):
    model = TeamMembership
    extra = 1


@admin.register(Team)
class TeamAdmin(ModelAdmin):
    list_display = ("name", "short_name", "country", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("name", "short_name", "country")
    inlines = [TeamMembershipInline]
