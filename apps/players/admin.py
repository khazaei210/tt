from django.contrib import admin

from .models import Player


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "gender", "club", "country", "is_active")
    list_filter = ("gender", "is_active", "country")
    search_fields = ("first_name", "last_name", "club", "country")
