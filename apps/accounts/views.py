from django.contrib.auth.views import LoginView


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"
