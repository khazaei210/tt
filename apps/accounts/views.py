from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import ListView

from apps.bale.services import send_password_reset_notification
from apps.core.permissions import StaffRequiredMixin, default_dashboard_url, staff_required, superuser_required

from .forms import StyledPasswordChangeForm
from .services import UsernameTakenError, create_account, reset_user_password

User = get_user_model()


class AccountLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_default_redirect_url(self):
        return default_dashboard_url(self.request.user)


class AccountPasswordChangeView(PasswordChangeView):
    """Any logged-in user (player or staff) changing their own password —
    the one thing every non-superuser account is allowed to do on its own
    account, everything else stays staff/superuser-gated elsewhere.
    Django's own PasswordChangeForm already verifies the current password
    and update_session_auth_hash() keeps the session valid afterward, so
    changing your password doesn't log you out."""

    form_class = StyledPasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _("Password changed."))
        return response


class AccountListView(StaffRequiredMixin, ListView):
    model = User
    context_object_name = "accounts"

    def get_queryset(self):
        qs = super().get_queryset().select_related("player_profile").order_by("username")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q)
                | Q(player_profile__first_name__icontains=q)
                | Q(player_profile__last_name__icontains=q)
            )
        return qs

    def get_template_names(self):
        if self.request.htmx:
            return ["accounts/_account_rows.html"]
        return ["accounts/account_list.html"]


@staff_required
def account_register(request):
    """Register a brand-new account (a referee, scorekeeper, or other
    staff login) not tied to any Player — that's players:create_login,
    reached from a specific player's edit page instead."""
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        make_staff = request.user.is_superuser and request.POST.get("is_staff") == "on"
        if not username:
            messages.error(request, _("Enter a username."))
            return render(request, "accounts/account_register.html", {"username": username})
        try:
            user, raw_password = create_account(username, is_staff=make_staff)
        except UsernameTakenError:
            messages.error(request, _("That username is already taken."))
            return render(request, "accounts/account_register.html", {"username": username})
        messages.success(
            request,
            _(
                "Account created — username: %(username)s, password: %(password)s "
                "(shown once now, save it before leaving this page)."
            )
            % {"username": user.username, "password": raw_password},
        )
        return redirect("accounts:list")
    return render(request, "accounts/account_register.html", {})


@staff_required
def account_toggle_active(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    account = get_object_or_404(User, pk=pk)
    if account.pk == request.user.pk:
        messages.error(request, _("You can't deactivate your own account."))
        return redirect("accounts:list")
    account.is_active = not account.is_active
    account.save(update_fields=["is_active"])
    if account.is_active:
        messages.success(request, _("%(username)s's account is now active.") % {"username": account.username})
    else:
        messages.success(request, _("%(username)s's account is now inactive.") % {"username": account.username})
    return redirect("accounts:list")


@staff_required
def account_reset_password(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    account = get_object_or_404(User, pk=pk)
    raw_password = reset_user_password(account)
    messages.success(
        request,
        _(
            "New password for %(username)s: %(password)s "
            "(shown once now, save it before leaving this page)."
        )
        % {"username": account.username, "password": raw_password},
    )
    player = getattr(account, "player_profile", None)
    if player is not None:
        status = send_password_reset_notification(player, account.username, raw_password)
        if status == "sent":
            messages.success(request, _("New password also sent to %(username)s via Bale.") % {"username": account.username})
        elif status == "not_linked":
            messages.warning(
                request,
                _("%(username)s hasn't linked their Bale account yet — the new password wasn't sent.")
                % {"username": account.username},
            )
        else:
            messages.warning(request, _("Sending the new password via Bale failed."))
    return redirect("accounts:list")


@superuser_required
def account_toggle_staff(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    account = get_object_or_404(User, pk=pk)
    if account.pk == request.user.pk:
        messages.error(request, _("You can't change your own staff access."))
        return redirect("accounts:list")
    account.is_staff = not account.is_staff
    account.save(update_fields=["is_staff"])
    if account.is_staff:
        messages.success(request, _("%(username)s can now manage the site.") % {"username": account.username})
    else:
        messages.success(request, _("%(username)s no longer has staff access.") % {"username": account.username})
    return redirect("accounts:list")


@staff_required
def account_delete(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    account = get_object_or_404(User, pk=pk)
    if account.pk == request.user.pk:
        messages.error(request, _("You can't delete your own account."))
        return redirect("accounts:list")
    account.delete()
    messages.success(request, _("Account deleted."))
    return redirect("accounts:list")
