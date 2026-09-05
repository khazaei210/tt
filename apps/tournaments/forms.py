from django import forms
from django.utils.translation import gettext_lazy as _

from apps.players.models import DoublesPair, Player
from apps.teams.models import Team

from .models import (
    Competition,
    CompetitionRule,
    Group,
    GroupParticipant,
    Participant,
    ParticipantType,
    Stage,
    Tournament,
)

INPUT_CLASS = "input input-bordered w-full"
SELECT_CLASS = "select select-bordered w-full"
TEXTAREA_CLASS = "textarea textarea-bordered w-full"


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ["name", "location", "start_date", "end_date", "status", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "location": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "start_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "status": forms.Select(attrs={"class": SELECT_CLASS}),
            "description": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3}),
        }


class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = ["name", "participant_type", "is_active", "ranking_category"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "participant_type": forms.Select(attrs={"class": SELECT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "ranking_category": forms.Select(attrs={"class": SELECT_CLASS}),
        }

    def __init__(self, *args, tournament=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tournament = tournament

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.tournament:
            instance.tournament = self.tournament
        if commit:
            instance.save()
        return instance


class CompetitionRuleForm(forms.ModelForm):
    class Meta:
        model = CompetitionRule
        fields = ["best_of_sets", "points_per_set", "win_by", "deciding_set_points", "cap_at"]
        widgets = {
            "best_of_sets": forms.Select(attrs={"class": SELECT_CLASS}),
            "points_per_set": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "win_by": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "deciding_set_points": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "cap_at": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
        }


class StageForm(forms.ModelForm):
    class Meta:
        model = Stage
        fields = ["name", "stage_format", "order", "qualifiers_per_group"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "stage_format": forms.Select(attrs={"class": SELECT_CLASS}),
            "order": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0}),
            "qualifiers_per_group": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
        }

    def __init__(self, *args, competition=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.competition:
            instance.competition = self.competition
        if commit:
            instance.save()
        return instance


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "order": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0}),
        }

    def __init__(self, *args, stage=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage = stage

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.stage:
            instance.stage = self.stage
        if commit:
            instance.save()
        return instance


class GroupParticipantForm(forms.ModelForm):
    class Meta:
        model = GroupParticipant
        fields = ["participant"]
        widgets = {
            "participant": forms.Select(attrs={"class": SELECT_CLASS}),
        }

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        if not group:
            return
        # A participant may only be placed in one group per stage.
        already_grouped_ids = GroupParticipant.objects.filter(group__stage=group.stage).values_list(
            "participant_id", flat=True
        )
        self.fields["participant"].queryset = group.stage.competition.participants.exclude(
            pk__in=already_grouped_ids
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.group = self.group
        if commit:
            instance.save()
        return instance


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = Participant
        fields = ["individual_player", "doubles_pair", "team", "seed"]
        widgets = {
            "individual_player": forms.Select(attrs={"class": SELECT_CLASS}),
            "doubles_pair": forms.Select(attrs={"class": SELECT_CLASS}),
            "team": forms.Select(attrs={"class": SELECT_CLASS}),
            "seed": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
        }

    def __init__(self, *args, competition=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition
        if not competition:
            return

        existing = competition.participants.exclude(pk=self.instance.pk).values_list(
            "individual_player_id", "doubles_pair_id", "team_id"
        )
        used_players = {row[0] for row in existing if row[0]}
        used_pairs = {row[1] for row in existing if row[1]}
        used_teams = {row[2] for row in existing if row[2]}

        if competition.participant_type == ParticipantType.INDIVIDUAL:
            del self.fields["doubles_pair"]
            del self.fields["team"]
            self.fields["individual_player"].queryset = Player.objects.exclude(pk__in=used_players)
            self.fields["individual_player"].required = True
        elif competition.participant_type == ParticipantType.DOUBLES:
            del self.fields["individual_player"]
            del self.fields["team"]
            self.fields["doubles_pair"].queryset = DoublesPair.objects.exclude(pk__in=used_pairs)
            self.fields["doubles_pair"].required = True
        elif competition.participant_type == ParticipantType.TEAM:
            del self.fields["individual_player"]
            del self.fields["doubles_pair"]
            self.fields["team"].queryset = Team.objects.exclude(pk__in=used_teams)
            self.fields["team"].required = True

    def clean_seed(self):
        seed = self.cleaned_data.get("seed")
        if seed is not None and self.competition:
            conflict = self.competition.participants.filter(seed=seed).exclude(pk=self.instance.pk)
            if conflict.exists():
                raise forms.ValidationError(_("Seed %(seed)s is already assigned to another participant.") % {"seed": seed})
        return seed

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.competition = self.competition
        instance.participant_type = self.competition.participant_type
        if commit:
            instance.save()
        return instance
