from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from apps.core.permissions import superuser_required

from .forms import BaleSettingsForm
from .models import BaleSettings


@superuser_required
def bale_settings(request):
    """Edit the bot token/username used for all Bale messaging — reset
    passwords, draw notifications, the /start linking flow. Superuser-only:
    this holds a live API credential, the same sensitivity as granting
    another account staff access (see accounts.account_toggle_staff)."""
    instance = BaleSettings.get_solo()
    if request.method == "POST":
        form = BaleSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, _("Bale settings saved."))
            return redirect("bale:settings")
    else:
        form = BaleSettingsForm(instance=instance)
    return render(request, "bale/settings.html", {"form": form})
