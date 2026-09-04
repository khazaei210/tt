from django.contrib import admin

from .models import Competition, CompetitionRule, Group, Participant, Stage, Tournament, TournamentStaff


class CompetitionInline(admin.TabularInline):
    model = Competition
    extra = 0


class TournamentStaffInline(admin.TabularInline):
    model = TournamentStaff
    extra = 0
    autocomplete_fields = ["user"]


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "start_date", "end_date", "status")
    list_filter = ("status",)
    search_fields = ("name", "location")
    inlines = [TournamentStaffInline, CompetitionInline]


@admin.register(TournamentStaff)
class TournamentStaffAdmin(admin.ModelAdmin):
    list_display = ("user", "tournament", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "tournament__name")
    autocomplete_fields = ["user"]


class StageInline(admin.TabularInline):
    model = Stage
    extra = 0


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "tournament", "participant_type", "is_active")
    list_filter = ("participant_type", "is_active")
    search_fields = ("name", "tournament__name")
    inlines = [StageInline, ParticipantInline]


@admin.register(CompetitionRule)
class CompetitionRuleAdmin(admin.ModelAdmin):
    list_display = ("competition", "best_of_sets", "points_per_set", "win_by")


class GroupInline(admin.TabularInline):
    model = Group
    extra = 0


@admin.register(Stage)
class StageAdmin(admin.ModelAdmin):
    list_display = ("name", "competition", "stage_format", "order")
    list_filter = ("stage_format",)
    inlines = [GroupInline]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "stage", "order")


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("display_name", "competition", "participant_type", "seed", "is_bye")
    list_filter = ("participant_type", "is_bye")
    search_fields = ("display_name",)
