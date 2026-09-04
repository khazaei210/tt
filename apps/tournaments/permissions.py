"""Per-tournament authorization.

CLAUDE.md's role list splits management (Tournament Admin / Manager) from
match operations (Referee / Scorekeeper) — see sections 20 and 21. Both
checks always let a Django superuser through (Super Admin), and both
degrade to "deny" for anonymous or role-less users, since every mutating
view in this app requires an explicit grant, never implicit trust.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import StaffRole, TournamentStaff

MANAGEMENT_ROLES = (StaffRole.TOURNAMENT_ADMIN, StaffRole.TOURNAMENT_MANAGER)
MATCH_ROLES = (
    StaffRole.TOURNAMENT_ADMIN,
    StaffRole.TOURNAMENT_MANAGER,
    StaffRole.REFEREE,
    StaffRole.SCOREKEEPER,
)


def has_tournament_role(user, tournament, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return TournamentStaff.objects.filter(tournament=tournament, user=user, role__in=roles).exists()


def can_manage_tournament(user, tournament):
    """Create/edit competitions, stages, groups, participants; generate
    schedules and brackets; edit the tournament itself."""
    return has_tournament_role(user, tournament, MANAGEMENT_ROLES)


def can_score_matches(user, tournament):
    """Enter and correct match scores."""
    return has_tournament_role(user, tournament, MATCH_ROLES)


def can_create_tournament(user):
    """Starting a brand new tournament isn't scoped to an existing
    Tournament yet, so it uses the same baseline staff gate as registry
    data — any staff/admin user can create one (and becomes its first
    Tournament Admin automatically, see views.TournamentCreateView)."""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


class TournamentManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """For CBVs that mutate data under a specific Tournament. Subclasses
    must implement get_tournament().

    Deliberately does NOT set raise_exception=True — see the identical
    note on core.permissions.StaffRequiredMixin; AccessMixin's default
    handle_no_permission() already redirects anonymous users to login and
    403s authenticated-but-unauthorized ones without any extra flag.
    """

    def get_tournament(self):
        raise NotImplementedError

    def test_func(self):
        return can_manage_tournament(self.request.user, self.get_tournament())


def tournament_manager_required(get_tournament_func):
    """Decorator for function-based views.

    get_tournament_func(request, *args, **kwargs) -> Tournament
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            tournament = get_tournament_func(request, *args, **kwargs)
            if not can_manage_tournament(request.user, tournament):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def match_scorer_required(get_tournament_func):
    """Decorator for function-based views that enter/correct scores.

    get_tournament_func(request, *args, **kwargs) -> Tournament
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            tournament = get_tournament_func(request, *args, **kwargs)
            if not can_score_matches(request.user, tournament):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
