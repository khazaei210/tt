from django.urls import path

from . import views

app_name = "matches"

urlpatterns = [
    path("dashboard/", views.scorer_dashboard, name="scorer_dashboard"),
    path("<int:pk>/", views.MatchDetailView.as_view(), name="detail"),
    path("<int:pk>/sets/save/", views.match_set_save, name="set_save"),
    path("<int:pk>/sets/<int:set_number>/delete/", views.match_set_delete, name="set_delete"),
    path("<int:pk>/start/", views.match_start, name="start"),
    path("<int:pk>/walkover/", views.match_walkover, name="walkover"),
    path("<int:pk>/retire/", views.match_retire, name="retire"),
    path("<int:pk>/default/", views.match_default, name="default"),
    path("<int:pk>/claim/", views.match_claim, name="claim"),
]
