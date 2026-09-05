from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("tournaments/<int:pk>/", views.tournament_report, name="tournament_report"),
    path("tournaments/<int:pk>/export.csv", views.tournament_report_csv, name="tournament_report_csv"),
    path("competitions/<int:pk>/results.csv", views.competition_results_csv, name="competition_results_csv"),
    path("players/<int:pk>/", views.player_statistics, name="player_statistics"),
]
