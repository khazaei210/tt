from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("players/", include("apps.players.urls")),
    path("teams/", include("apps.teams.urls")),
    path("tournaments/", include("apps.tournaments.urls")),
    path("matches/", include("apps.matches.urls")),
    path("rankings/", include("apps.rankings.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", include("apps.core.urls")),
    prefix_default_language=True,
)

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]
