from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class BaleSettings(models.Model):
    """Singleton row holding the Bale bot's token/username, editable from
    the web UI (bale:settings, superuser-only) instead of requiring an
    env var change plus a container restart on every credential rotation.

    Blank fields fall back to the BALE_BOT_TOKEN/BALE_BOT_USERNAME env
    vars (see effective_token/effective_username) — an existing
    env-var-only deployment keeps working unconfigured through the UI.
    """

    bot_token = models.CharField(_("Bot token"), max_length=200, blank=True)
    bot_username = models.CharField(_("Bot username"), max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Bale settings")
        verbose_name_plural = _("Bale settings")

    def __str__(self):
        return str(_("Bale settings"))

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def effective_token(self):
        return self.bot_token or settings.BALE_BOT_TOKEN

    @property
    def effective_username(self):
        return self.bot_username or settings.BALE_BOT_USERNAME
