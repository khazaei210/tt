from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import JalaliDateField, JalaliDateWidget

from .models import DoublesPair, Player
from .phone import normalize_mobile_number

INPUT_CLASS = "input input-bordered w-full"
SELECT_CLASS = "select select-bordered w-full"


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = [
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "club",
            "country",
            "mobile_number",
            "is_active",
        ]
        field_classes = {
            "date_of_birth": JalaliDateField,
        }
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "gender": forms.Select(attrs={"class": SELECT_CLASS}),
            "date_of_birth": JalaliDateWidget(attrs={"class": INPUT_CLASS}),
            "club": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "mobile_number": forms.TextInput(attrs={"class": INPUT_CLASS, "dir": "ltr", "placeholder": "0912xxxxxxx"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def clean_mobile_number(self):
        # Model.save() normalizes this too, but that runs after this form's
        # own uniqueness check (ModelForm._post_clean -> validate_unique) —
        # without normalizing here first, two differently-formatted inputs
        # for the same real number (e.g. "0912..." vs "+98912...") would
        # compare as different strings, pass validation, and only collide
        # as a raw IntegrityError once both hit save().
        normalized = normalize_mobile_number(self.cleaned_data.get("mobile_number", ""))
        if not normalized:
            raise forms.ValidationError(_("Enter a valid mobile number."))
        return normalized


class PlayerRegistrationForm(PlayerForm):
    """PlayerForm plus a username, used only when registering a brand new
    player (PlayerCreateView) — every player is created with a login
    together in one step, rather than staff optionally adding one later.
    Not a model field: views.PlayerCreateView.form_valid() saves the
    Player first, then hands this to accounts.services.create_player_login,
    the same service the "create login" flow on an existing player's edit
    page already uses (including its silent-dedupe-with-suffix behavior
    for a taken username)."""

    username = forms.CharField(
        label=_("Username"),
        required=False,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "dir": "ltr"}),
        help_text=_("Leave blank to generate one from the player's name."),
    )


class DoublesPairForm(forms.ModelForm):
    class Meta:
        model = DoublesPair
        fields = ["player_one", "player_two"]
        widgets = {
            "player_one": forms.Select(attrs={"class": SELECT_CLASS}),
            "player_two": forms.Select(attrs={"class": SELECT_CLASS}),
        }

    def clean(self):
        cleaned_data = super().clean()
        player_one = cleaned_data.get("player_one")
        player_two = cleaned_data.get("player_two")
        if player_one and player_two:
            if player_one == player_two:
                raise forms.ValidationError(_("A pair must contain two different players."))
            low, high = sorted([player_one, player_two], key=lambda p: p.pk)
            existing = DoublesPair.objects.filter(player_one=low, player_two=high)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_("This pair already exists."))
        return cleaned_data
