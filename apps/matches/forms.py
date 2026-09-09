from django import forms
from django.utils.translation import gettext_lazy as _

INPUT_CLASS = "input input-bordered w-20 text-center"
SELECT_CLASS = "select select-bordered w-full"


class SetScoreForm(forms.Form):
    participant_a_score = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={"class": INPUT_CLASS}))
    participant_b_score = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={"class": INPUT_CLASS}))


class TieLineupForm(forms.Form):
    """One side's nominated order of play (ITTF A/B/C) for a team tie —
    the 3 dropdowns are scoped to that team's active roster."""

    player_a = forms.ModelChoiceField(queryset=None, label=_("Player A"), widget=forms.Select(attrs={"class": SELECT_CLASS}))
    player_b = forms.ModelChoiceField(queryset=None, label=_("Player B"), widget=forms.Select(attrs={"class": SELECT_CLASS}))
    player_c = forms.ModelChoiceField(queryset=None, label=_("Player C"), widget=forms.Select(attrs={"class": SELECT_CLASS}))

    def __init__(self, *args, team, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        from apps.players.models import Player

        roster = Player.objects.filter(team_memberships__team=team, team_memberships__is_active=True).order_by(
            "last_name", "first_name"
        )
        for field in ("player_a", "player_b", "player_c"):
            self.fields[field].queryset = roster

    def clean(self):
        cleaned = super().clean()
        players = [cleaned.get("player_a"), cleaned.get("player_b"), cleaned.get("player_c")]
        if all(players) and len({p.id for p in players}) != 3:
            raise forms.ValidationError(_("Nominate 3 different players for A, B and C."))
        return cleaned

    def players(self):
        return [self.cleaned_data["player_a"], self.cleaned_data["player_b"], self.cleaned_data["player_c"]]
