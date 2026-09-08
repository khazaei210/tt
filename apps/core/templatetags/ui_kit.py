"""Reusable Tailwind/DaisyUI UI components (CLAUDE.md section 24: "Prefer
reusable UI components for: buttons, cards, badges, tables, ... Maintain a
coherent design system").

These replace the hand-written Tailwind class strings that were repeated,
with small drift between copies, across most templates in the project —
page headers, panel/table wrappers, status badges, stat tiles, and empty
states. Every tag renders plain DaisyUI markup; there is nothing here that
couldn't be written out by hand, it's just centralized so the classes only
live in one place.

`pageheader` is a full Node (not `simple_block_tag`) because it needs two
independent content slots — subtitle and actions — split by a delimiter
tag, the same way `{% if %}...{% else %}...{% endif %}` splits into two
branches. Everything else only ever needs one slot (or none), so
`simple_block_tag` / `simple_tag` (Django 5.2+) is enough.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


# Heroicons-outline-style paths (24x24 viewBox, stroke-based) — same hand-
# inlined style already used in templates/base.html's nav, kept here so
# every icon button in the app draws from one small shared set instead of
# each template pasting its own SVG (CLAUDE.md section 24: one coherent
# design system, no mixed icon sources/libraries).
_ICON_PATHS = {
    "edit": (
        "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 "
        "2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
    ),
    "delete": (
        "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 "
        "4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
    ),
    "add": "M12 4v16m8-8H4",
    "back": "M10 19l-7-7m0 0l7-7m-7 7h18",
    "export": "M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3",
    # Symmetric (points both ways) so it reads correctly regardless of
    # text direction — unlike a single left/right arrow, which would
    # point the wrong way in the app's RTL layout.
    "swipe": "M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5",
}


@register.simple_tag
def icon(name, extra_class="h-4 w-4"):
    """One inline `<svg>` icon by name (see `_ICON_PATHS`). Pair with
    visually-hidden-below-a-breakpoint label text for an icon-only button
    on mobile that still shows its label at wider screens — the icon
    alone is not an accessible name, so callers must still put a real
    label (an `aria-label` on the button/link, or visible text) on the
    containing element."""
    path = _ICON_PATHS.get(name, "")
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" class="{}" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" d="{}" /></svg>',
        extra_class,
        path,
    )


class PageHeaderNode(template.Node):
    def __init__(self, title_var, nodelist_subtitle, nodelist_actions):
        self.title_var = title_var
        self.nodelist_subtitle = nodelist_subtitle
        self.nodelist_actions = nodelist_actions

    def render(self, context):
        title = self.title_var.resolve(context)
        subtitle_html = self.nodelist_subtitle.render(context).strip()
        actions_html = self.nodelist_actions.render(context).strip() if self.nodelist_actions else ""

        subtitle_block = (
            format_html('<p class="text-base-content/60">{}</p>', mark_safe(subtitle_html)) if subtitle_html else ""
        )
        actions_block = (
            format_html('<div class="flex gap-2 flex-wrap">{}</div>', mark_safe(actions_html))
            if actions_html
            else ""
        )
        return format_html(
            '<div class="flex items-center justify-between mb-4 gap-4 flex-wrap">'
            "<div><h1 class=\"text-2xl font-bold\">{}</h1>{}</div>{}</div>",
            title,
            mark_safe(subtitle_block),
            mark_safe(actions_block),
        )


@register.tag("pageheader")
def do_pageheader(parser, token):
    """A page's title + optional subtitle + optional action buttons.

    Usage::

        {% pageheader tournament.name %}
            {{ tournament.location|default:"—" }}
        {% pageheader_actions %}
            <a href="{% url 'tournaments:edit' tournament.pk %}" class="btn btn-outline">{% translate "Edit" %}</a>
        {% endpageheader %}

    The subtitle block (everything before `{% pageheader_actions %}`, or
    the whole body if that tag is omitted) may contain arbitrary markup —
    links, badges, blocktranslate — not just plain text. Leave a block
    empty (or omit `pageheader_actions` entirely) to skip that part.
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError("%r takes exactly one argument: the title" % bits[0])
    title_var = parser.compile_filter(bits[1])

    nodelist_subtitle = parser.parse(("pageheader_actions", "endpageheader"))
    end_token = parser.next_token()
    if end_token.contents == "pageheader_actions":
        nodelist_actions = parser.parse(("endpageheader",))
        parser.delete_first_token()
    else:
        nodelist_actions = None
    return PageHeaderNode(title_var, nodelist_subtitle, nodelist_actions)


@register.simple_block_tag
def sectionheader(content, title):
    """A smaller in-page section heading (`<h2>`) with an optional action
    button/group on the right — the same shape as `pageheader` one size
    down, for a subsection within a page rather than the page itself."""
    actions = content.strip() if content else ""
    actions_block = format_html('<div class="flex gap-2 flex-wrap">{}</div>', mark_safe(actions)) if actions else ""
    return format_html(
        '<div class="flex items-center justify-between mb-2 gap-2 flex-wrap">'
        '<h2 class="text-lg font-semibold">{}</h2>{}</div>',
        title,
        mark_safe(actions_block),
    )


@register.simple_block_tag
def card(content, extra_class=""):
    """A generic content panel: `bg-base-100 rounded-box shadow p-4`."""
    css = f"bg-base-100 rounded-box shadow p-4 {extra_class}".strip()
    return format_html('<div class="{}">{}</div>', css, mark_safe(str(content)))


@register.simple_block_tag
def form_card(content, title, subtitle=""):
    """The centered `max-w-lg` panel around a create/edit form: an `<h1>`
    title, an optional one-line subtitle (e.g. the parent object's name),
    then the form itself as block content."""
    subtitle_block = format_html('<p class="text-base-content/60 mb-4">{}</p>', subtitle) if subtitle else ""
    return format_html(
        '<div class="max-w-lg mx-auto bg-base-100 rounded-box shadow p-6">'
        '<h1 class="text-2xl font-bold mb-6">{}</h1>{}{}</div>',
        title,
        mark_safe(subtitle_block),
        mark_safe(str(content)),
    )


@register.simple_block_tag
def table_card(content, table_class="", extra_class=""):
    """The `overflow-x-auto` + shadowed-panel wrapper around a `<table>`.
    Block content is the table's `<thead>`/`<tbody>`."""
    wrapper_css = f"overflow-x-auto bg-base-100 rounded-box shadow {extra_class}".strip()
    table_css = f"table {table_class}".strip()
    return format_html('<div class="{}"><table class="{}">{}</table></div>', wrapper_css, table_css, mark_safe(str(content)))


@register.simple_tag
def empty_row(message, colspan=1):
    """A `{% empty %}` row for a table body: a single centered, muted message."""
    return format_html(
        '<tr><td colspan="{}" class="text-center text-base-content/60 py-6">{}</td></tr>', colspan, message
    )


@register.simple_tag
def status_badge(label, variant="outline", size=""):
    """A DaisyUI badge. variant: outline/success/error/ghost/warning/...;
    size: "" (default) / xs / sm / lg."""
    classes = f"badge badge-{variant}" + (f" badge-{size}" if size else "")
    return format_html('<span class="{}">{}</span>', classes, label)


@register.simple_block_tag
def stats_row(content, extra_class="", compact=False):
    """Wrapper for a row of `stat` tiles. compact=True is the smaller,
    unshadowed variant used for a stat row nested inside another card."""
    if compact:
        css = f"stats stats-vertical sm:stats-horizontal bg-base-200 {extra_class}".strip()
    else:
        css = f"stats stats-vertical lg:stats-horizontal shadow bg-base-100 w-full {extra_class}".strip()
    return format_html('<div class="{}">{}</div>', css, mark_safe(str(content)))


@register.simple_tag
def stat(title, value, description="", value_class="", compact=False):
    """One tile inside a `stats_row`. compact=True matches that wrapper's
    smaller variant (smaller title/value text, tighter padding)."""
    stat_css = "stat py-2" if compact else "stat"
    value_css = ("stat-value text-lg" if compact else "stat-value") + (f" {value_class}" if value_class else "")
    title_css = "stat-title text-xs" if compact else "stat-title"
    desc_html = format_html('<div class="stat-desc">{}</div>', description) if description else ""
    return format_html(
        '<div class="{}"><div class="{}">{}</div><div class="{}">{}</div>{}</div>',
        stat_css,
        title_css,
        title,
        value_css,
        value,
        desc_html,
    )


@register.simple_tag
def empty_panel(message, extra_class=""):
    """A plain single-line empty-state panel: `bg-base-100 rounded-box
    shadow p-6 text-base-content/60`. Smaller than `hero_empty_state` —
    for a lone message with no title or call-to-action."""
    css = f"bg-base-100 rounded-box shadow p-6 text-base-content/60 {extra_class}".strip()
    return format_html('<div class="{}">{}</div>', css, message)


@register.simple_tag
def hero_empty_state(title, description, cta_url="", cta_label=""):
    """The larger "nothing here yet" placeholder for a whole page (as
    opposed to `empty_row`, which is for one row of a table)."""
    p_class = "text-base-content/60 mb-4" if cta_url else "text-base-content/60"
    cta_html = format_html('<a href="{}" class="btn btn-primary">{}</a>', cta_url, cta_label) if cta_url else ""
    return format_html(
        '<div class="hero bg-base-100 rounded-box shadow py-16"><div class="hero-content text-center">'
        '<div class="max-w-md"><h2 class="text-xl font-semibold mb-2">{}</h2>'
        '<p class="{}">{}</p>{}</div></div></div>',
        title,
        p_class,
        description,
        cta_html,
    )
