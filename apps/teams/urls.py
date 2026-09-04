from django.urls import path

from . import views

app_name = "teams"

urlpatterns = [
    path("", views.TeamListView.as_view(), name="list"),
    path("add/", views.TeamCreateView.as_view(), name="add"),
    path("<int:pk>/", views.TeamDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.TeamUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.team_delete, name="delete"),
    path("<int:pk>/members/add/", views.team_member_add, name="member_add"),
    path("<int:pk>/members/<int:membership_id>/remove/", views.team_member_remove, name="member_remove"),
]
