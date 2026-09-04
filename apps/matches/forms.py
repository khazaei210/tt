from django import forms

INPUT_CLASS = "input input-bordered w-20 text-center"


class SetScoreForm(forms.Form):
    participant_a_score = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={"class": INPUT_CLASS}))
    participant_b_score = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={"class": INPUT_CLASS}))
