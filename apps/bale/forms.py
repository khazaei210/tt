from django import forms
from django.utils.translation import gettext_lazy as _

from .models import BaleSettings

INPUT_CLASS = "input input-bordered w-full"


class BaleSettingsForm(forms.ModelForm):
    class Meta:
        model = BaleSettings
        fields = ["bot_token", "bot_username"]
        widgets = {
            "bot_token": forms.PasswordInput(
                render_value=True,
                attrs={"class": INPUT_CLASS, "dir": "ltr", "autocomplete": "off"},
            ),
            "bot_username": forms.TextInput(
                attrs={"class": INPUT_CLASS, "dir": "ltr", "autocomplete": "off", "placeholder": "JamTTbot"}
            ),
        }
        help_texts = {
            "bot_token": _("From @BotFather on Bale. Leave blank to fall back to the BALE_BOT_TOKEN env var."),
            "bot_username": _(
                "Shown to staff on a player's edit page so they know which bot to message. "
                "Leave blank to fall back to the BALE_BOT_USERNAME env var."
            ),
        }
