from django.contrib import admin

from .models import EloRating, EloRatingEvent, PlayerRanking, RankingCategory, RankingEvent, RankingPointsScale


class RankingPointsScaleInline(admin.TabularInline):
    model = RankingPointsScale
    extra = 1


@admin.register(RankingCategory)
class RankingCategoryAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [RankingPointsScaleInline]


@admin.register(PlayerRanking)
class PlayerRankingAdmin(admin.ModelAdmin):
    list_display = ["player", "category", "current_rank", "points", "tournaments_played"]
    list_filter = ["category"]
    search_fields = ["player__first_name", "player__last_name"]


@admin.register(RankingEvent)
class RankingEventAdmin(admin.ModelAdmin):
    list_display = ["player", "category", "competition", "placement", "points_awarded", "created_at"]
    list_filter = ["category"]
    search_fields = ["player__first_name", "player__last_name"]
    readonly_fields = ["created_at"]


@admin.register(EloRating)
class EloRatingAdmin(admin.ModelAdmin):
    list_display = ["player", "category", "current_rank", "rating", "matches_played"]
    list_filter = ["category"]
    search_fields = ["player__first_name", "player__last_name"]


@admin.register(EloRatingEvent)
class EloRatingEventAdmin(admin.ModelAdmin):
    list_display = ["player", "category", "match", "won", "delta", "rating_after", "created_at"]
    list_filter = ["category", "won"]
    search_fields = ["player__first_name", "player__last_name"]
    readonly_fields = ["created_at"]
