from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    AccountListView,
    AccountLoginView,
    account_delete,
    account_register,
    account_reset_password,
    account_toggle_active,
    account_toggle_staff,
)

app_name = "accounts"

urlpatterns = [
    path("login/", AccountLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("manage/", AccountListView.as_view(), name="list"),
    path("manage/register/", account_register, name="register"),
    path("manage/<int:pk>/toggle-active/", account_toggle_active, name="toggle_active"),
    path("manage/<int:pk>/reset-password/", account_reset_password, name="reset_password"),
    path("manage/<int:pk>/toggle-staff/", account_toggle_staff, name="toggle_staff"),
    path("manage/<int:pk>/delete/", account_delete, name="delete"),
]
