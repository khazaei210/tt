from django.urls import path

from . import views

app_name = "players"

urlpatterns = [
    path("", views.PlayerListView.as_view(), name="list"),
    path("add/", views.PlayerCreateView.as_view(), name="add"),
    path("<int:pk>/edit/", views.PlayerUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.player_delete, name="delete"),
    path("pairs/", views.DoublesPairListView.as_view(), name="pair_list"),
    path("pairs/add/", views.DoublesPairCreateView.as_view(), name="pair_add"),
    path("pairs/<int:pk>/delete/", views.doubles_pair_delete, name="pair_delete"),
]
