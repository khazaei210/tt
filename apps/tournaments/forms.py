from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import JalaliDateField, JalaliDateWidget
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
from .services.registration import is_competition_full

INPUT_CLASS = "input input-bordered w-full"
SELECT_CLASS = "select select-bordered w-full"
TEXTAREA_CLASS = "textarea textarea-bordered w-full"


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ["name", "location", "start_date", "end_date", "status", "description"]
        field_classes = {
            "start_date": JalaliDateField,
            "end_date": JalaliDateField,
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "location": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "start_date": JalaliDateWidget(attrs={"class": INPUT_CLASS}),
            "end_date": JalaliDateWidget(attrs={"class": INPUT_CLASS}),
            "status": forms.Select(attrs={"class": SELECT_CLASS}),
            "description": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3}),
        }


class CompetitionForm(forms.ModelForm):
    class Meta:
        model = Competition
        fields = [
            "name",
            "participant_type",
            "is_active",
            "ranking_category",
            "registration_open",
            "registration_capacity",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "participant_type": forms.Select(attrs={"class": SELECT_CLASS}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "ranking_category": forms.Select(attrs={"class": SELECT_CLASS}),
            "registration_open": forms.CheckboxInput(attrs={"class": "checkbox"}),
            "registration_capacity": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
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
        # is_tie_slot=False, not .entrants(): this form already didn't
        # filter out BYE participants (existing behavior, unrelated to
        # the tie-slot leak this closes), so only exclude tie-slot ones.
        self.fields["participant"].queryset = group.stage.competition.participants.filter(
            is_tie_slot=False
        ).exclude(pk__in=already_grouped_ids)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.group = self.group
        if commit:
            instance.save()
        return instance


_PARTICIPANT_FIELD_BY_TYPE = {
    ParticipantType.INDIVIDUAL: "individual_player",
    ParticipantType.DOUBLES: "doubles_pair",
    ParticipantType.TEAM: "team",
}


def _eligible_participants(competition, *, exclude_pk=None):
    """(field_name, queryset) of the players/doubles pairs/teams — whichever
    matches this competition's participant_type — that aren't already
    entered in it. Shared by ParticipantForm (one at a time, with a seed)
    and BulkParticipantForm (many at once, unseeded) so both always agree
    on who's still eligible to be added.
    """
    existing = competition.participants.exclude(pk=exclude_pk).values_list(
        "individual_player_id", "doubles_pair_id", "team_id"
    )
    used_players = {row[0] for row in existing if row[0]}
    used_pairs = {row[1] for row in existing if row[1]}
    used_teams = {row[2] for row in existing if row[2]}

    field_name = _PARTICIPANT_FIELD_BY_TYPE[competition.participant_type]
    queryset = {
        "individual_player": Player.objects.exclude(pk__in=used_players),
        "doubles_pair": DoublesPair.objects.exclude(pk__in=used_pairs),
        "team": Team.objects.exclude(pk__in=used_teams),
    }[field_name]
    return field_name, queryset


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

        field_name, queryset = _eligible_participants(competition, exclude_pk=self.instance.pk)
        for name in ("individual_player", "doubles_pair", "team"):
            if name != field_name:
                del self.fields[name]
        self.fields[field_name].queryset = queryset
        self.fields[field_name].required = True

    def clean_seed(self):
        seed = self.cleaned_data.get("seed")
        if seed is not None and self.competition:
            conflict = self.competition.participants.filter(seed=seed).exclude(pk=self.instance.pk)
            if conflict.exists():
                raise forms.ValidationError(_("Seed %(seed)s is already assigned to another participant.") % {"seed": seed})
        return seed

    def clean(self):
        cleaned_data = super().clean()
        if self.competition and not self.instance.pk and is_competition_full(self.competition):
            raise forms.ValidationError(_("This competition has reached its registration capacity."))
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.competition = self.competition
        instance.participant_type = self.competition.participant_type
        if commit:
            instance.save()
        return instance


class BulkParticipantForm(forms.Form):
    """Add several participants to a competition in one submit — a
    checklist instead of ParticipantForm's one-at-a-time picker, for
    registering a full field of players/pairs/teams without a separate
    page load per entry. Deliberately doesn't take a seed (seeding a
    whole field at once isn't a single value) — added participants stay
    unseeded, same as ParticipantForm leaves it if the seed field is left
    blank.
    """

    def __init__(self, *args, competition=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.competition = competition
        self._field_name, queryset = _eligible_participants(competition)
        self.fields["selected"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            required=True,
            widget=forms.CheckboxSelectMultiple,
            label="",
        )

    def clean_selected(self):
        selected = self.cleaned_data["selected"]
        if self.competition.registration_capacity is not None:
            remaining = self.competition.registration_capacity - self.competition.participants.entrants().count()
            if len(selected) > max(remaining, 0):
                raise forms.ValidationError(
                    _("Only %(remaining)s more participant(s) can be added before reaching capacity.")
                    % {"remaining": max(remaining, 0)}
                )
        return selected

    def save(self):
        participants = []
        for obj in self.cleaned_data["selected"]:
            participant = Participant(
                competition=self.competition,
                participant_type=self.competition.participant_type,
                **{self._field_name: obj},
            )
            participant.save()
            participants.append(participant)
        return participants


class GroupBulkCreateForm(forms.Form):
    count = forms.IntegerField(
        label=_("Number of groups"),
        min_value=1,
        max_value=32,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1, "max": 32}),
    )


class GroupParticipantMoveForm(forms.Form):
    target_group = forms.ModelChoiceField(queryset=Group.objects.none(), widget=forms.Select(attrs={"class": SELECT_CLASS}))

    def __init__(self, *args, group_participant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group_participant = group_participant
        self.fields["target_group"].queryset = Group.objects.filter(
            stage_id=group_participant.group.stage_id
        ).exclude(pk=group_participant.group_id)


class BracketSwapForm(forms.Form):
    participant_a = forms.ModelChoiceField(queryset=Participant.objects.none(), widget=forms.Select(attrs={"class": SELECT_CLASS}))
    participant_b = forms.ModelChoiceField(queryset=Participant.objects.none(), widget=forms.Select(attrs={"class": SELECT_CLASS}))

    def __init__(self, *args, stage=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage = stage
        queryset = stage.competition.participants.entrants()
        self.fields["participant_a"].queryset = queryset
        self.fields["participant_b"].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        a = cleaned_data.get("participant_a")
        b = cleaned_data.get("participant_b")
        if a and b and a.pk == b.pk:
            raise forms.ValidationError(_("Choose two different participants to swap."))
        return cleaned_data
