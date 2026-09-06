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
            format_html('<div class="flex gap-2">{}</div>', mark_safe(actions_html)) if actions_html else ""
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
    actions_block = format_html('<div class="flex gap-2">{}</div>', mark_safe(actions)) if actions else ""
    return format_html(
        '<div class="flex items-center justify-between mb-2"><h2 class="text-lg font-semibold">{}</h2>{}</div>',
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
