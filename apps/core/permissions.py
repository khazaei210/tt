"""Generic, app-agnostic permission helpers.

Tournament-scoped role checks (Tournament Admin/Manager/Referee/
Scorekeeper) live in apps.tournaments.permissions, since they need the
TournamentStaff model. This module only has the baseline "is this an
authenticated staff/admin user" gate, used for registry data (Players,
Teams, DoublesPairs) that isn't owned by any single tournament.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse


def is_staff_user(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def default_dashboard_url(user):
    """Where an authenticated user lands on login and on "/" (CLAUDE.md
    section 25/26): a player-only account (no staff access) always has its
    own dashboard; every other authenticated account (staff, superuser —
    covers Tournament Admin/Manager/Referee/Scorekeeper, whose specific
    role is scoped per-tournament rather than a single global flag) lands
    on the Tournament Manager dashboard, which is the closest thing this
    app has to a general staff landing page.
    """
    if not user.is_staff and not user.is_superuser and getattr(user, "player_profile", None):
        return reverse("players:dashboard")
    return reverse("tournaments:manager_dashboard")


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """For CBVs that mutate registry data.

    Deliberately does NOT set raise_exception=True: AccessMixin's default
    handle_no_permission() already does the right thing on its own —
    it raises PermissionDenied (403) whenever the user is authenticated
    (so a logged-in non-staff user gets a clear 403, not a login redirect
    loop) and only redirects to the login page for a genuinely anonymous
    user. Setting raise_exception=True here would override that and send
    anonymous users straight to a 403 too, which is wrong.
    """

    def test_func(self):
        return is_staff_user(self.request.user)


def staff_required(view_func):
    """For function-based views that mutate registry data."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not is_staff_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def superuser_required(view_func):
    """For function-based views that change another account's staff/
    superuser status — a plain staff account granting itself or a peer
    that access would be a privilege escalation, so this is stricter than
    staff_required."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
