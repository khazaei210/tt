from django import forms
from django.utils.translation import gettext_lazy as _

from .models import DoublesPair, Player

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
            "is_active",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "gender": forms.Select(attrs={"class": SELECT_CLASS}),
            "date_of_birth": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "club": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


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
