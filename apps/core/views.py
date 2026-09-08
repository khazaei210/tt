from django.shortcuts import redirect, render

from apps.rankings.services import build_category_leaderboard, get_default_ranking_category

from .permissions import default_dashboard_url


def home(request):
    """The public landing page (CLAUDE.md section 25): an anonymous
    visitor sees the single global ranking table (the "Overall"
    RankingCategory every competition auto-attaches to, see
    apps.rankings.services.get_default_ranking_category) with each player
    linking to their overall stats; an authenticated user is sent straight
    to their own dashboard instead — this page has nothing further to show
    them.
    """
    if request.user.is_authenticated:
        return redirect(default_dashboard_url(request.user))

    category = get_default_ranking_category()
    rows = build_category_leaderboard(category)
    return render(request, "core/home.html", {"category": category, "rows": rows})
