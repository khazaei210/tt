from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class RankingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rankings"
    verbose_name = _("Rankings")
