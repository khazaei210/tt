from django.contrib import admin

from .models import Match, MatchCorrection, MatchSet


class MatchSetInline(admin.TabularInline):
    model = MatchSet
    extra = 0


class MatchCorrectionInline(admin.TabularInline):
    model = MatchCorrection
    extra = 0
    readonly_fields = ("action", "set_number", "previous_value", "new_value", "performed_by", "created_at")
    can_delete = False


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "competition", "group", "round_number", "status", "winner", "referee", "scorekeeper")
    list_filter = ("status", "competition")
    autocomplete_fields = ("referee", "scorekeeper")
    search_fields = ("participant_a__display_name", "participant_b__display_name")
    inlines = [MatchSetInline, MatchCorrectionInline]


@admin.register(MatchCorrection)
class MatchCorrectionAdmin(admin.ModelAdmin):
    list_display = ("match", "action", "set_number", "previous_value", "new_value", "performed_by", "created_at")
    list_filter = ("action",)
    readonly_fields = ("match", "action", "set_number", "previous_value", "new_value", "performed_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
