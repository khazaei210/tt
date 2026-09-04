from django import forms

from apps.players.models import Player

from .models import Team, TeamMembership

INPUT_CLASS = "input input-bordered w-full"
SELECT_CLASS = "select select-bordered w-full"


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "short_name", "country", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "short_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "country": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


class TeamMembershipForm(forms.ModelForm):
    class Meta:
        model = TeamMembership
        fields = ["player", "joined_on"]
        widgets = {
            "player": forms.Select(attrs={"class": SELECT_CLASS}),
            "joined_on": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        existing_member_ids = team.memberships.values_list("player_id", flat=True) if team else []
        self.fields["player"].queryset = Player.objects.exclude(pk__in=existing_member_ids)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.team = self.team
        if commit:
            instance.save()
        return instance
