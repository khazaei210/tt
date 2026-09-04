from django.db import connection
from django.shortcuts import render
from django.utils.translation import gettext as _


def home(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        (postgres_version,) = cursor.fetchone()

    context = {
        "postgres_version": postgres_version,
    }
    return render(request, "core/home.html", context)


def htmx_ping(request):
    if request.htmx:
        message = _("HTMX request received and handled server-side.")
    else:
        message = _("This endpoint is meant to be called via HTMX.")
    return render(request, "core/_ping_result.html", {"message": message})
