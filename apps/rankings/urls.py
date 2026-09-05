from django.urls import path

from . import views

app_name = "rankings"

urlpatterns = [
    path("", views.category_list, name="category_list"),
    path("me/", views.my_rankings, name="my_rankings"),
    path("<int:pk>/", views.category_detail, name="category_detail"),
    path("<int:pk>/export.csv", views.category_csv, name="category_csv"),
    path("competitions/<int:pk>/award/", views.award_points, name="award_points"),
]
