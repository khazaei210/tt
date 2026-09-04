from django.contrib import admin

from .models import DoublesPair, Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "gender", "club", "country", "is_active")
    list_filter = ("gender", "is_active", "country")
    search_fields = ("first_name", "last_name", "club", "country")


@admin.register(DoublesPair)
class DoublesPairAdmin(admin.ModelAdmin):
    list_display = ("__str__", "created_at")
    search_fields = ("player_one__first_name", "player_one__last_name", "player_two__first_name", "player_two__last_name")
