from django.urls import path

from . import views

app_name = "tournaments"

urlpatterns = [
    path("", views.TournamentListView.as_view(), name="list"),
    path("add/", views.TournamentCreateView.as_view(), name="add"),
    path("<int:pk>/", views.TournamentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.TournamentUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.tournament_delete, name="delete"),
    path("<int:tournament_pk>/competitions/add/", views.CompetitionCreateView.as_view(), name="competition_add"),
    path("competitions/<int:pk>/", views.CompetitionDetailView.as_view(), name="competition_detail"),
    path("competitions/<int:pk>/edit/", views.CompetitionUpdateView.as_view(), name="competition_edit"),
    path("competitions/<int:pk>/delete/", views.competition_delete, name="competition_delete"),
    path("competitions/<int:pk>/rule/", views.competition_rule_edit, name="competition_rule_edit"),
    path("competitions/<int:competition_pk>/stages/add/", views.StageCreateView.as_view(), name="stage_add"),
    path("stages/<int:pk>/", views.StageDetailView.as_view(), name="stage_detail"),
    path("stages/<int:pk>/edit/", views.StageUpdateView.as_view(), name="stage_edit"),
    path("stages/<int:pk>/delete/", views.stage_delete, name="stage_delete"),
    path("stages/<int:stage_pk>/groups/add/", views.GroupCreateView.as_view(), name="group_add"),
    path("groups/<int:pk>/delete/", views.group_delete, name="group_delete"),
    path(
        "competitions/<int:competition_pk>/participants/add/",
        views.participant_add,
        name="participant_add",
    ),
    path(
        "competitions/<int:competition_pk>/participants/<int:pk>/delete/",
        views.participant_delete,
        name="participant_delete",
    ),
]
