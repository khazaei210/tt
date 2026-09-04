from django.urls import path

from . import views

app_name = "matches"

urlpatterns = [
    path("<int:pk>/", views.MatchDetailView.as_view(), name="detail"),
    path("<int:pk>/sets/save/", views.match_set_save, name="set_save"),
    path("<int:pk>/sets/<int:set_number>/delete/", views.match_set_delete, name="set_delete"),
]
