from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("tournaments/<int:pk>/", views.tournament_report, name="tournament_report"),
    path("players/<int:pk>/", views.player_statistics, name="player_statistics"),
]
