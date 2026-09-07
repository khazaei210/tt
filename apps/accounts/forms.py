from django.contrib.auth.forms import PasswordChangeForm

INPUT_CLASS = "input input-bordered w-full"


class StyledPasswordChangeForm(PasswordChangeForm):
    """PasswordChangeForm isn't a ModelForm, so widget classes can't be
    set via Meta — applied here instead, matching the input styling used
    everywhere else in the app."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": INPUT_CLASS, "dir": "ltr"})
