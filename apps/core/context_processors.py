"""Site-wide template context.

Currently just the DaisyUI theme picker's option list (base.html's sidebar
theme switcher). Keep this in sync with the `themes:` line in
theme/src/input.css — that line controls which themes' CSS actually gets
built, this one controls which of those are offered in the picker.
"""

AVAILABLE_THEMES = [
    "fantasy",
    "light",
    "dark",
    "cupcake",
    "bumblebee",
    "corporate",
    "business",
    "luxury",
    "night",
    "winter",
    "dracula",
    "autumn",
    "forest",
    "emerald",
    "synthwave",
    "valentine",
]


def theme_options(request):
    return {"AVAILABLE_THEMES": AVAILABLE_THEMES}
