from django import forms

from .models import Player

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
