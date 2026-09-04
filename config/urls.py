from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("players/", include("apps.players.urls")),
    path("teams/", include("apps.teams.urls")),
    path("", include("apps.core.urls")),
    prefix_default_language=True,
)

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]
