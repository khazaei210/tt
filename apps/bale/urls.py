from django.urls import path

from . import views

app_name = "bale"

urlpatterns = [
    path("settings/", views.bale_settings, name="settings"),
]
