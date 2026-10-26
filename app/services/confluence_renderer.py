"""Convert Confluence storage-format XHTML into safe, semantic reader HTML.

The local mirror stores exactly one body representation: Confluence **storage-format
XHTML** (custom ``ac:`` / ``ri:`` namespaces). Browsers cannot render those elements,
so this module normalises them once, through a single ordered pipeline, into plain
semantic HTML that the reader styles under ``.confluence-content``.

Design rules that this module must keep:

* **One canonical path.** ``ac:adf-extension`` blocks carry both an ``ac:adf-content``
  body (canonical) and an ``ac:adf-fallback`` copy (legacy pre-rendered HTML). Only
  the canonical body is emitted, so no macro body is ever rendered twice.
* **Nothing executable.** Plain-text macro bodies (code, no-format) are HTML-escaped,
  and inline ``color`` / ``background-color`` declarations are dropped. The frontend
  additionally sanitises with an explicit allowlist.
* **Nothing silently dropped.** Unsupported or malformed macros become a named,
  neutral fallback that keeps whatever safe authored text and links they carried.
* **No invented content.** Values that are absent stay absent; nothing is guessed.

Escaping plain-text bodies is the single most important behaviour here: runbooks are
full of commands such as ``kubectl -n <namespace> top pod -l app=<deployment>``.
Emitted raw, ``<namespace>`` becomes an unknown element that the sanitiser deletes,
silently corrupting the command an engineer is about to run.
"""

import html as html_lib
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Render context
# ---------------------------------------------------------------------------

class RenderContext:
    """Per-page information the renderer needs to resolve references.

    Every field is optional: with an empty context the renderer still produces
    correct output, it just cannot resolve attachments or internal page links and
    falls back to honest placeholders instead of guessing.
    """

    __slots__ = ('space_key', 'page_id', 'page_url', 'site_base_url',
                 'attachments', 'resolve_page')

    def __init__(self, space_key=None, page_id=None, page_url=None,
                 site_base_url=None, attachments=None, resolve_page=None):
        self.space_key = space_key
        self.page_id = page_id
        self.page_url = page_url
        self.site_base_url = site_base_url
        # filename -> attachment dict (as stored in the attachment manifest)
        self.attachments = attachments or {}
        # callable(space_key, title) -> (space_key, page_id) or None
        self.resolve_page = resolve_page

    def attachment(self, filename):
        return self.attachments.get(filename)

    def attachment_url(self, filename):
        """Local download URL for an attachment, or None when unavailable."""
        if not (self.space_key and self.page_id):
            return None
        return (f'/api/spaces/{self.space_key}/pages/{self.page_id}'
                f'/attachments/{_url_quote(filename)}')

    def local_page_url(self, space_key, title):
        """Local mirror URL for an internal page link, or None when absent."""
        if not self.resolve_page:
            return None
        try:
            found = self.resolve_page(space_key or self.space_key, title)
        except Exception:  # a lookup failure must never break rendering
            logger.debug('Page resolution failed for %r/%r', space_key, title)
            return None
        if not found:
            return None
        target_space, target_id = found
        return f'/spaces/{target_space}/pages/{target_id}/{_slugify(title)}'

    def confluence_page_url(self, space_key, title):
        """Canonical Confluence URL for a page we do not mirror."""
        if not self.site_base_url:
            return None
        space = space_key or self.space_key
        if not space:
            return None
        return (f'{self.site_base_url.rstrip("/")}/spaces/{space}'
                f'/pages?title={_url_quote(title)}')


_EMPTY_CONTEXT = RenderContext()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _esc(text):
    """Escape text for use in HTML element content."""
    return html_lib.escape(text or '', quote=False)


def _esc_attr(text):
    """Escape text for use inside a double-quoted HTML attribute."""
    return html_lib.escape(text or '', quote=True)


def _url_quote(text):
    from urllib.parse import quote
    return quote(text or '', safe='')


def _strip_tags(fragment):
    """Plain text of an HTML fragment, with entities left intact."""
    return re.sub(r'<[^>]+>', '', fragment or '').strip()


def _slugify(text):
    """Stable, URL-safe slug used for heading anchors and page links."""
    text = _strip_tags(html_lib.unescape(text or ''))
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text or 'section'


def _is_safe_url(url):
    """Allow only navigable, non-active URL forms."""
    if not url:
        return False
    candidate = html_lib.unescape(url).strip().lower()
    candidate = candidate.replace('\t', '').replace('\n', '').replace('\r', '')
    if re.match(r'^(?:https?:|mailto:|/|\#|\?|\.{0,2}/)', candidate):
        return True
    # A bare relative path such as "page.html" is safe; anything with a scheme is not.
    return ':' not in candidate.split('/')[0]


def _param(body, name):
    """Value of an ``ac:parameter`` by name, or ''."""
    match = re.search(
        rf'<ac:parameter\s+ac:name="{re.escape(name)}"\s*>(.*?)</ac:parameter>',
        body, flags=re.DOTALL | re.IGNORECASE
    )
    return match.group(1).strip() if match else ''


def _rich_body(body):
    """Inner HTML of ``ac:rich-text-body``, or None."""
    match = re.search(r'<ac:rich-text-body\s*>(.*?)</ac:rich-text-body>',
                      body, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def _plain_body(body):
    """Text of ``ac:plain-text-body`` (CDATA or plain), or None."""
    match = re.search(
        r'<ac:plain-text-body\s*>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>',
        body, flags=re.DOTALL | re.IGNORECASE
    )
    if match:
        return match.group(1)
    match = re.search(r'<ac:plain-text-body\s*>(.*?)</ac:plain-text-body>',
                      body, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return html_lib.unescape(match.group(1))
    return None


# ---------------------------------------------------------------------------
# Callout (panel) mapping
# ---------------------------------------------------------------------------

# Confluence panel type -> (semantic variant, accessible label).
#
# The variant drives a CSS class only; the visual palette lives in
# frontend/src/index.css. Tailwind utility classes are deliberately NOT emitted
# here, because Tailwind only scans frontend sources — utilities generated in
# Python never reach the compiled stylesheet, which is what produced the
# unreadable light-on-light callouts.
PANEL_VARIANTS = {
    'info': ('info', 'Info'),
    'note': ('note', 'Note'),
    'tip': ('success', 'Tip'),
    'success': ('success', 'Success'),
    'warning': ('warning', 'Warning'),
    'error': ('danger', 'Error'),
    'custom': ('neutral', 'Panel'),
}


def _callout(panel_type, inner_html):
    """Render a theme-aware callout with a textual label and an icon glyph.

    Status is never conveyed by colour alone: every callout carries a visible
    text label, and the icon is marked decorative so it is not announced twice.
    """
    variant, label = PANEL_VARIANTS.get(
        (panel_type or '').strip().lower(), ('neutral', 'Note')
    )
    return (
        f'<div class="cf-callout cf-callout-{variant}" role="note" '
        f'aria-label="{_esc_attr(label)}">'
        f'<p class="cf-callout-label"><span class="cf-callout-icon" aria-hidden="true">'
        f'</span>{_esc(label)}</p>'
        f'<div class="cf-callout-body">{inner_html}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Unsupported macro fallback
# ---------------------------------------------------------------------------

# Macros the reader cannot reproduce locally. Each renders as a neutral, named
# block that keeps any authored text so nothing disappears silently.
UNSUPPORTED_MACRO_LABELS = {
    'view-file': 'Embedded file',
    'viewxls': 'Embedded spreadsheet',
    'viewpdf': 'Embedded PDF',
    'drawio': 'Draw.io diagram',
    'inc-drawio': 'Draw.io diagram',
    'gliffy': 'Gliffy diagram',
    'contentbylabel': 'Content by label (dynamic list)',
    'children': 'Child pages (dynamic list)',
    'pagetree': 'Page tree (dynamic list)',
    'livesearch': 'Live search',
    'listlabels': 'Label list',
    'recently-updated': 'Recently updated (dynamic list)',
    'content-report-table': 'Content report table (dynamic list)',
    'create-from-template': 'Create-from-template button',
    'widget': 'Embedded widget',
    'iframe': 'Embedded frame',
    'multimedia': 'Embedded media',
    'profile': 'User profile',
    'include': 'Included page',
    'excerpt-include': 'Included excerpt',
    'chart': 'Chart',
    'roadmap': 'Roadmap planner',
    'calendar': 'Team calendar',
    'jiraissues': 'Jira issue list',
    'jira-chart': 'Jira chart',
    'toc-zone': 'Table of contents zone',
}

# Macros that are pure markers around their own body. Unwrapping them loses
# nothing a reader would notice, so they are unwrapped silently.
TRANSPARENT_MACROS = {
    'excerpt',   # marks a reusable region; the body is ordinary content
    'section',   # legacy layout wrapper
    'column',    # legacy layout wrapper
}

# Macros the reader can render faithfully but that carry meaning in their name.
# The body is kept verbatim and given a visible heading.
LABELLED_BODY_MACROS = {
    'details': 'Page properties',
}


# Macros the renderer maps explicitly somewhere in the pipeline. A *self-closing*
# instance of one of these carries neither a body nor parameters (both are child
# elements), so it is an empty authoring leftover and renders as nothing.
# Without this, an empty `<ac:structured-macro ac:name="code" />` reached the
# generic handler and claimed "Unsupported macro: code" — which is untrue and
# adds noise to a page that renders perfectly.
SUPPORTED_MACRO_NAMES = frozenset({
    'code', 'noformat', 'status', 'expand', 'anchor', 'toc', 'jira',
    'info', 'note', 'tip', 'success', 'warning', 'error', 'panel',
    'excerpt', 'section', 'column', 'details',
})


def _labelled_section(label, inner_html):
    """A named section around a macro body the reader can render faithfully."""
    return (
        f'<section class="cf-macro-section" aria-label="{_esc_attr(label)}">'
        f'<p class="cf-macro-section-label">{_esc(label)}</p>'
        f'{inner_html}</section>'
    )


def _unsupported(macro_name, body, context):
    """Neutral, honest fallback for a macro the reader cannot reproduce."""
    label = UNSUPPORTED_MACRO_LABELS.get(
        macro_name, f'Unsupported macro: {macro_name}'
    )

    # Keep any authored detail the macro carried, so nothing is lost.
    detail_parts = []
    filename = _param(body, 'name') or _param(body, 'filename')
    if filename:
        # view-file stores the filename as a nested ri:attachment reference.
        ri_name = re.search(r'ri:filename="([^"]+)"', filename)
        detail_parts.append(ri_name.group(1) if ri_name else _strip_tags(filename))
    else:
        ri_name = re.search(r'ri:filename="([^"]+)"', body)
        if ri_name:
            detail_parts.append(ri_name.group(1))
    for param in ('title', 'label', 'labels', 'cql', 'spaces', 'page'):
        value = _strip_tags(_param(body, param))
        if value:
            detail_parts.append(value)

    detail_html = ''
    if detail_parts:
        joined = ' · '.join(_esc(part) for part in dict.fromkeys(detail_parts))
        detail_html = f'<p class="cf-unsupported-detail">{joined}</p>'

    # Preserve an authored rich body verbatim when one exists.
    rich = _rich_body(body)
    body_html = f'<div class="cf-unsupported-body">{rich}</div>' if rich else ''
    if not rich:
        plain = _plain_body(body)
        if plain and plain.strip():
            body_html = (f'<pre class="cf-code"><code>{_esc(plain)}</code></pre>')

    link_html = ''
    if context.page_url:
        link_html = (
            f'<p class="cf-unsupported-link">'
            f'<a href="{_esc_attr(context.page_url)}" target="_blank" '
            f'rel="noopener noreferrer">Open in Confluence</a></p>'
        )

    return (
        f'<div class="cf-unsupported" data-macro="{_esc_attr(macro_name)}" role="note" '
        f'aria-label="{_esc_attr(label)}">'
        f'<p class="cf-unsupported-label">'
        f'<span class="cf-unsupported-icon" aria-hidden="true"></span>'
        f'{_esc(label)}</p>'
        f'{detail_html}{body_html}{link_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def storage_body_is_empty(html):
    """True when a storage-format body carries nothing a reader could see.

    A non-blank file is not the same as a page with content: 108 items in this
    mirror are literally ``<p />``. Distinguishing the two is what lets the reader
    say "this page has no content" instead of implying that rendering failed.
    """
    if not html or not html.strip():
        return True
    text = re.sub(r'<[^>]+>', ' ', html)
    text = text.replace('&nbsp;', ' ').replace('\xa0', ' ').strip()
    if text:
        return False
    has_media = re.search(r'<ac:image|<ri:attachment|<ac:structured-macro|<ac:adf-extension',
                          html, re.IGNORECASE)
    return not has_media


def render_storage_format(html, user_lookup=None, context=None):
    """Convert Confluence storage-format XHTML into safe semantic reader HTML.

    Args:
        html: Raw storage-format body from the local mirror.
        user_lookup: Optional account-id -> display name map for mentions.
        context: Optional :class:`RenderContext` for attachment and link resolution.

    Returns:
        HTML string. Never raises: any unexpected failure degrades to the escaped
        source text so a page can still be read.
    """
    if not html:
        return html

    ctx = context or _EMPTY_CONTEXT
    users = user_lookup or {}

    try:
        result = html

        # -- Structure first: collapse ADF extensions to a single body ---------
        result = _convert_adf_extensions(result, ctx)
        result = _unwrap_adf_marks(result)

        # -- Inline constructs ------------------------------------------------
        result = _convert_placeholders(result)
        result = _convert_emoticons(result)
        result = _convert_mentions(result, users)
        result = _convert_status_macros(result)
        result = _convert_jira_macros(result)
        result = _convert_task_lists(result)

        # -- Block macros -----------------------------------------------------
        result = _convert_code_macros(result)
        result = _convert_panel_macros(result)
        result = _convert_expand_macros(result)
        result = _convert_anchor_macros(result)
        result = _drop_toc_macros(result)
        result = _convert_unsupported_macros(result, ctx)
        result = _convert_remaining_macros(result, ctx)

        # -- References -------------------------------------------------------
        result = _convert_images(result, ctx)
        result = _convert_links(result, ctx)

        # -- Layout -----------------------------------------------------------
        result = _convert_layout(result)

        # -- Residual namespace cleanup (keeps inner text) --------------------
        result = re.sub(r'</?ac:[^>]*>', '', result)
        result = re.sub(r'</?ri:[^>]*/?>', '', result)

        # -- Safety and tidy-up ----------------------------------------------
        result = _strip_active_content(result)
        result = _sanitize_inline_styles(result)
        result = _wrap_tables(result)
        result = _normalize_headings(result)
        result = _drop_empty_paragraphs(result)

        return result
    except Exception:
        # A rendering bug must never blank a runbook. Fall back to escaped source
        # so the text remains readable and nothing executes.
        logger.exception('Renderer failed for page %s; falling back to escaped source',
                         ctx.page_id)
        return f'<pre class="cf-code"><code>{_esc(html)}</code></pre>'


# ---------------------------------------------------------------------------
# ADF extensions
# ---------------------------------------------------------------------------

def _convert_adf_extensions(html, context):
    """Collapse ``ac:adf-extension`` to exactly one rendered body.

    Confluence Cloud emits::

        <ac:adf-extension>
          <ac:adf-node type="panel">
            <ac:adf-attribute key="panel-type">note</ac:adf-attribute>
            <ac:adf-content> ...canonical content... </ac:adf-content>
          </ac:adf-node>
          <ac:adf-fallback> ...pre-rendered duplicate... </ac:adf-fallback>
        </ac:adf-extension>

    The canonical ``ac:adf-content`` wins and the fallback is discarded, which is
    what stops panels rendering twice and stops the raw ``panel-type`` value
    leaking into the page as a stray "note" label.
    """

    def replace(match):
        block = match.group(1)

        node_type = ''
        node_match = re.search(r'<ac:adf-node[^>]*\btype="([^"]+)"', block, re.IGNORECASE)
        if node_match:
            node_type = node_match.group(1).strip().lower()

        content_match = re.search(r'<ac:adf-content\s*>(.*?)</ac:adf-content>',
                                  block, flags=re.DOTALL | re.IGNORECASE)

        if not content_match:
            # No canonical body: keep the legacy fallback rather than lose content.
            fallback = re.search(r'<ac:adf-fallback\s*>(.*?)</ac:adf-fallback>',
                                 block, flags=re.DOTALL | re.IGNORECASE)
            if fallback:
                return fallback.group(1)
            if node_type:
                return _unsupported(f'adf-{node_type}', block, context)
            return ''

        inner = content_match.group(1)

        if node_type == 'panel':
            panel_type = ''
            attr = re.search(
                r'<ac:adf-attribute\s+key="panel-type"\s*>([^<]+)</ac:adf-attribute>',
                block, flags=re.IGNORECASE
            )
            if attr:
                panel_type = attr.group(1)
            return _callout(panel_type or 'info', inner)

        if node_type in ('decision-list', 'decision-item'):
            return f'<div class="cf-decision">{inner}</div>'

        if node_type == 'expand':
            title = ''
            attr = re.search(
                r'<ac:adf-attribute\s+key="title"\s*>([^<]*)</ac:adf-attribute>',
                block, flags=re.IGNORECASE
            )
            if attr:
                title = attr.group(1).strip()
            return _details(title or 'Details', inner)

        # Any other node type: keep the canonical content unwrapped.
        return inner

    return re.sub(r'<ac:adf-extension\s*>(.*?)</ac:adf-extension>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


def _unwrap_adf_marks(html):
    """Drop ADF annotation wrappers, keeping the text they wrap."""
    for tag in ('adf-mark', 'adf-fragment-mark', 'adf-fragment-mark-detail',
                'inline-comment-marker'):
        html = re.sub(rf'</?ac:{tag}\b[^>]*/?>', '', html, flags=re.IGNORECASE)
    return html


# ---------------------------------------------------------------------------
# Inline constructs
# ---------------------------------------------------------------------------

def _convert_placeholders(html):
    """Mark unfilled editor placeholders instead of passing them off as content.

    ``ac:placeholder`` holds template ghost text ("Type /link to add a ticket",
    "@ owner"). Confluence's own view renderer omits it. The text is kept — so
    nothing is lost — but flagged so a reader is never misled into treating a
    template hint as an instruction.
    """

    def replace(match):
        text = _strip_tags(match.group(1))
        if not text:
            return ''
        return ('<span class="cf-placeholder">'
                '<span class="cf-visually-hidden">Unfilled template placeholder: </span>'
                f'{_esc(text)}</span>')

    return re.sub(r'<ac:placeholder[^>]*>(.*?)</ac:placeholder>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


# Confluence emoticon name -> (glyph, accessible label). Emoticons carried real
# meaning in these runbooks (534 blue-star bullets, 33 warning markers), so
# stripping them lost author intent.
EMOTICON_GLYPHS = {
    'blue-star': ('\u2605', 'star'),
    'yellow-star': ('\u2605', 'star'),
    'green-star': ('\u2605', 'star'),
    'red-star': ('\u2605', 'star'),
    'star': ('\u2605', 'star'),
    'warning': ('\u26a0', 'warning'),
    'information': ('\u2139', 'information'),
    'tick': ('\u2714', 'tick'),
    'check': ('\u2714', 'tick'),
    'white-check-mark': ('\u2714', 'tick'),
    'cross': ('\u2716', 'cross'),
    'question': ('?', 'question'),
    'thumbs-up': ('\U0001f44d', 'thumbs up'),
    'thumbs-down': ('\U0001f44e', 'thumbs down'),
    'smile': ('\U0001f642', 'smile'),
    'sad': ('\U0001f641', 'sad'),
    'wink': ('\U0001f609', 'wink'),
    'laugh': ('\U0001f604', 'laugh'),
    'pencil': ('\u270f', 'pencil'),
    'edit': ('\u270f', 'edit'),
    'plus': ('+', 'plus'),
    'minus': ('\u2212', 'minus'),
    'key': ('\U0001f511', 'key'),
    'light-on': ('\U0001f4a1', 'idea'),
    'clipboard': ('\U0001f4cb', 'clipboard'),
    'muscle': ('\U0001f4aa', 'muscle'),
    'scroll': ('\U0001f4dc', 'scroll'),
    'calendar_spiral': ('\U0001f5d3', 'calendar'),
    'chart_with_upwards_trend': ('\U0001f4c8', 'upward chart'),
}


def _convert_emoticons(html):
    """Render ``ac:emoticon`` as a labelled glyph instead of dropping it."""

    def replace(match):
        name = (match.group(1) or '').strip().lower()
        glyph, label = EMOTICON_GLYPHS.get(name, ('\u2022', name or 'emoticon'))
        return (f'<span class="cf-emoticon" role="img" '
                f'aria-label="{_esc_attr(label)}">{glyph}</span>')

    return re.sub(r'<ac:emoticon[^>]*\bac:name="([^"]*)"[^>]*/?>',
                  replace, html, flags=re.IGNORECASE)


def _convert_mentions(html, user_lookup):
    """Render ``ri:user`` mentions as a chip.

    When the account id cannot be resolved the chip says so rather than inventing
    a name.
    """

    def replace(match):
        account_id = match.group(1)
        name = user_lookup.get(account_id)
        if name:
            return f'<span class="cf-mention">@{_esc(name)}</span>'
        return ('<span class="cf-mention cf-mention-unresolved" '
                'title="Mentioned user is not resolvable from the local mirror">'
                '@Unknown user</span>')

    return re.sub(
        r'<ac:link[^>]*>\s*<ri:user\s+[^>]*ri:account-id="([^"]+)"[^>]*/>\s*'
        r'(?:<ac:link-body>.*?</ac:link-body>\s*)?</ac:link>',
        replace, html, flags=re.DOTALL | re.IGNORECASE
    )


# Confluence status colour -> (variant, label suffix). The variant only chooses a
# palette; the lozenge always shows its own text, so colour is never the only cue.
STATUS_VARIANTS = {
    'green': 'success',
    'yellow': 'warning',
    'red': 'danger',
    'blue': 'info',
    'purple': 'note',
    'grey': 'neutral',
    'gray': 'neutral',
}


def _convert_status_macros(html):
    """Render the status macro as a text lozenge."""

    def replace(match):
        body = match.group(1)
        title = _strip_tags(_param(body, 'title'))
        colour = _strip_tags(_param(body, 'colour')).lower()
        variant = STATUS_VARIANTS.get(colour, 'neutral')
        if not title:
            return ''
        return (f'<span class="cf-status cf-status-{variant}">'
                f'<span class="cf-visually-hidden">Status: </span>'
                f'{_esc(title)}</span>')

    return re.sub(r'<ac:structured-macro\s+[^>]*ac:name="status"[^>]*>(.*?)</ac:structured-macro>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


def _convert_jira_macros(html):
    """Render the Jira macro as an issue-key chip.

    The mirror stores no resolved Jira data (no summary, status, or base URL), so
    the chip shows the authored key only and claims nothing further.
    """

    def replace(match):
        body = match.group(1)
        key = _strip_tags(_param(body, 'key'))
        if key:
            return (f'<span class="cf-issue-key">'
                    f'<span class="cf-visually-hidden">Jira issue </span>'
                    f'{_esc(key)}</span>')
        jql = _strip_tags(_param(body, 'jqlQuery'))
        if jql:
            return ('<span class="cf-issue-key cf-issue-query">'
                    f'<span class="cf-visually-hidden">Jira query </span>'
                    f'{_esc(jql)}</span>')
        return ''

    return re.sub(r'<ac:structured-macro\s+[^>]*ac:name="jira"[^>]*>(.*?)</ac:structured-macro>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


def _convert_task_lists(html):
    """Render ``ac:task-list`` as a real list with visible completion state.

    Completion is conveyed by a glyph plus visually-hidden text, never by colour.
    """

    def replace_task(match):
        block = match.group(1)
        status_match = re.search(r'<ac:task-status\s*>(.*?)</ac:task-status>', block,
                                 flags=re.DOTALL | re.IGNORECASE)
        status = _strip_tags(status_match.group(1)).lower() if status_match else ''
        body_match = re.search(r'<ac:task-body\s*>(.*?)</ac:task-body>', block,
                               flags=re.DOTALL | re.IGNORECASE)
        body = body_match.group(1) if body_match else ''
        done = status == 'complete'
        glyph = '\u2611' if done else '\u2610'
        state = 'Done' if done else 'To do'
        state_class = ' cf-task-done' if done else ''
        return (f'<li class="cf-task{state_class}">'
                f'<span class="cf-task-box" aria-hidden="true">{glyph}</span>'
                f'<span class="cf-visually-hidden">{state}: </span>'
                f'<span class="cf-task-text">{body}</span></li>')

    html = re.sub(r'<ac:task\b[^>]*>(.*?)</ac:task\s*>', replace_task, html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ac:task-list\b[^>]*>(.*?)</ac:task-list\s*>',
                  lambda m: f'<ul class="cf-task-list">{m.group(1)}</ul>',
                  html, flags=re.DOTALL | re.IGNORECASE)
    # Some pages carry tasks without an enclosing ac:task-list. A bare <li> is
    # invalid and unusable with a screen reader, so wrap each orphan run in a list.
    def wrap_orphans(match):
        return f'<ul class="cf-task-list">{match.group(0)}</ul>'

    html = re.sub(r'(?:<li class="cf-task[^"]*">.*?</li>\s*)+',
                  lambda m: m.group(0) if _inside_list(html, m.start()) else wrap_orphans(m),
                  html, flags=re.DOTALL)
    return html


def _inside_list(html, index):
    """True when the offset sits inside an already-open ``ul``/``ol``."""
    before = html[:index]
    opens = len(re.findall(r'<(?:ul|ol)\b', before, flags=re.IGNORECASE))
    closes = len(re.findall(r'</(?:ul|ol)\s*>', before, flags=re.IGNORECASE))
    return opens > closes


# ---------------------------------------------------------------------------
# Block macros
# ---------------------------------------------------------------------------

def _convert_code_macros(html):
    """Render code / no-format macros as escaped ``<pre><code>`` blocks.

    Escaping is mandatory. Runbook commands routinely contain angle-bracket
    placeholders (``kubectl -n <namespace> ...``) and sample markup
    (``<script src="..."></script>``). Emitted raw, those become unknown elements
    that the sanitiser deletes, silently corrupting the command.
    """

    def replace(match):
        macro = (match.group(1) or '').lower()
        body = match.group(2)
        code = _plain_body(body)
        if code is None:
            code = ''
        language = _strip_tags(_param(body, 'language'))
        title = _strip_tags(_param(body, 'title'))

        attrs = ' class="cf-code"'
        if language and macro == 'code':
            attrs += f' data-language="{_esc_attr(language)}"'

        title_html = ''
        if title:
            title_html = f'<figcaption class="cf-code-title">{_esc(title)}</figcaption>'

        block = f'<pre{attrs}><code>{_esc(code)}</code></pre>'
        if title_html:
            return f'<figure class="cf-code-figure">{title_html}{block}</figure>'
        return block

    return re.sub(
        r'<ac:structured-macro\s+[^>]*ac:name="(code|noformat|no-format)"[^>]*>'
        r'(.*?)</ac:structured-macro>',
        replace, html, flags=re.DOTALL | re.IGNORECASE
    )


def _convert_panel_macros(html):
    """Render classic info / note / warning / tip / error / panel macros."""

    def replace(match):
        name = (match.group(1) or '').lower()
        body = match.group(2)
        inner = _rich_body(body)
        if inner is None:
            plain = _plain_body(body)
            inner = f'<p>{_esc(plain)}</p>' if plain else ''
        if name == 'panel':
            title = _strip_tags(_param(body, 'title'))
            if title:
                inner = f'<p class="cf-panel-title"><strong>{_esc(title)}</strong></p>{inner}'
            return _callout('custom', inner)
        return _callout(name, inner)

    return re.sub(
        r'<ac:structured-macro\s+[^>]*ac:name="(info|note|tip|success|warning|error|panel)"'
        r'[^>]*>(.*?)</ac:structured-macro>',
        replace, html, flags=re.DOTALL | re.IGNORECASE
    )


def _details(title, inner_html):
    """Native disclosure markup for expand-style macros."""
    return (f'<details class="cf-expand"><summary class="cf-expand-summary">'
            f'{_esc(title)}</summary>'
            f'<div class="cf-expand-body">{inner_html}</div></details>')


def _convert_expand_macros(html):
    """Render expand macros as a native ``<details>`` disclosure."""

    def replace(match):
        body = match.group(1)
        title = _strip_tags(_param(body, 'title')) or 'Details'
        inner = _rich_body(body) or ''
        return _details(title, inner)

    return re.sub(r'<ac:structured-macro\s+[^>]*ac:name="expand"[^>]*>(.*?)</ac:structured-macro>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


def _convert_anchor_macros(html):
    """Keep authored anchors so existing fragment links continue to resolve."""

    def replace(match):
        body = match.group(1)
        # The anchor macro stores its name in the unnamed (ac:name="") parameter,
        # occasionally as "name"; fall back to the first parameter of any name.
        name = _strip_tags(_param(body, '')) or _strip_tags(_param(body, 'name'))
        if not name:
            first = re.search(r'<ac:parameter[^>]*>(.*?)</ac:parameter>', body,
                              flags=re.DOTALL | re.IGNORECASE)
            name = _strip_tags(first.group(1)) if first else ''
        if not name:
            return ''
        return f'<span class="cf-anchor" id="{_esc_attr(_slugify(name))}"></span>'

    return re.sub(r'<ac:structured-macro\s+[^>]*ac:name="anchor"[^>]*>(.*?)</ac:structured-macro>',
                  replace, html, flags=re.DOTALL | re.IGNORECASE)


def _drop_toc_macros(html):
    """Remove inline TOC macros; the reader's right rail provides navigation.

    Nothing authored is lost: the macro has no body, it only asked Confluence to
    generate a heading list, which the reader now does from the rendered headings.
    """
    return re.sub(
        r'<ac:structured-macro\s+[^>]*ac:name="toc"[^>]*(?:/>|>.*?</ac:structured-macro>)',
        '', html, flags=re.DOTALL | re.IGNORECASE
    )


def _convert_unsupported_macros(html, context):
    """Render known-unsupported macros as named neutral fallbacks."""
    names = '|'.join(re.escape(n) for n in UNSUPPORTED_MACRO_LABELS)

    def replace(match):
        return _unsupported((match.group(1) or '').lower(), match.group(2), context)

    # Container form first, then self-closing.
    html = re.sub(
        rf'<ac:structured-macro\s+[^>]*ac:name="({names})"[^>]*>(.*?)</ac:structured-macro>',
        replace, html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(
        rf'<ac:structured-macro\s+[^>]*ac:name="({names})"[^>]*/>',
        lambda m: _unsupported((m.group(1) or '').lower(), '', context),
        html, flags=re.IGNORECASE
    )
    return html


def _convert_remaining_macros(html, context):
    """Handle any macro not matched above.

    The default is the named fallback, not a silent unwrap: an unrecognised
    macro keeps its authored text *and* says which macro produced it, so a
    reader can tell that the original experience is missing. Only the macros in
    ``TRANSPARENT_MACROS`` and ``LABELLED_BODY_MACROS`` are exempt, because for
    those the authored body genuinely is the whole content.

    A census of the mirror (scripts/macro_census.py) shows this path is reached
    by ``details`` (4 occurrences) and ``excerpt`` (1); everything else is
    mapped explicitly upstream.
    """

    def replace(match):
        name = (match.group(1) or '').lower()
        body = match.group(2)

        if name in TRANSPARENT_MACROS:
            rich = _rich_body(body)
            if rich is not None and rich.strip():
                return rich

        if name in LABELLED_BODY_MACROS:
            rich = _rich_body(body)
            if rich is not None and rich.strip():
                return _labelled_section(LABELLED_BODY_MACROS[name], rich)

        return _unsupported(name, body, context)

    def replace_self_closing(match):
        name = (match.group(1) or '').lower()
        # An empty instance of a macro we do support is an authoring leftover.
        if name in SUPPORTED_MACRO_NAMES:
            return ''
        return _unsupported(name, '', context)

    html = re.sub(
        r'<ac:structured-macro\s+[^>]*ac:name="([^"]+)"[^>]*>(.*?)</ac:structured-macro>',
        replace, html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(
        r'<ac:structured-macro\s+[^>]*ac:name="([^"]+)"[^>]*/>',
        replace_self_closing, html, flags=re.IGNORECASE
    )
    return html


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _convert_images(html, context):
    """Render ``ac:image`` as a figure.

    * External ``ri:url`` images become a real responsive ``<img>``.
    * Attachment images become a real ``<img>`` when the bytes are mirrored, and
      an explicit "not mirrored" placeholder when they are not. The placeholder
      states the reason instead of leaving a blank gap or implying a broken image.

    Alt text comes only from the source; none is invented.
    """

    def replace(match):
        block = match.group(0)
        attrs = match.group(1) or ''

        alt_match = re.search(r'ac:alt="([^"]*)"', attrs, re.IGNORECASE)
        alt = alt_match.group(1) if alt_match else None

        caption_match = re.search(r'<ac:caption\s*>(.*?)</ac:caption>', block,
                                  flags=re.DOTALL | re.IGNORECASE)
        caption = caption_match.group(1) if caption_match else ''
        caption_html = (f'<figcaption class="cf-figcaption">{caption}</figcaption>'
                        if caption.strip() else '')

        url_match = re.search(r'<ri:url\s+[^>]*ri:value="([^"]+)"', block, re.IGNORECASE)
        if url_match and _is_safe_url(url_match.group(1)):
            src = html_lib.unescape(url_match.group(1))
            alt_attr = _esc_attr(alt) if alt is not None else ''
            return (f'<figure class="cf-figure">'
                    f'<img class="cf-image" src="{_esc_attr(src)}" alt="{alt_attr}" '
                    f'loading="lazy" decoding="async" />{caption_html}</figure>')

        file_match = re.search(r'<ri:attachment\s+[^>]*ri:filename="([^"]+)"',
                               block, re.IGNORECASE)
        if not file_match:
            return _image_placeholder(alt or '', None, caption_html, context)

        filename = html_lib.unescape(file_match.group(1))
        attachment = context.attachment(filename)
        if attachment and attachment.get('downloaded'):
            url = context.attachment_url(filename)
            if url:
                alt_attr = _esc_attr(alt if alt is not None else filename)
                return (f'<figure class="cf-figure">'
                        f'<img class="cf-image" src="{_esc_attr(url)}" alt="{alt_attr}" '
                        f'loading="lazy" decoding="async" />{caption_html}</figure>')

        return _image_placeholder(alt or '', filename, caption_html, context)

    html = re.sub(r'<ac:image\b([^>]*)>.*?</ac:image>', replace, html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ac:image\b([^>]*)/>', replace, html, flags=re.IGNORECASE)
    return html


def _image_placeholder(alt, filename, caption_html, context):
    """Explicit placeholder for an image whose bytes are not mirrored locally."""
    name = filename or alt or 'Image'
    link_html = ''
    if context.page_url:
        link_html = (f'<a class="cf-image-missing-link" '
                     f'href="{_esc_attr(context.page_url)}" target="_blank" '
                     f'rel="noopener noreferrer">Open in Confluence</a>')
    # No role="img" here: the placeholder carries readable text and may contain a
    # link, and an img role would both hide that text and nest an interactive
    # control inside a non-interactive image role.
    return (
        f'<figure class="cf-figure cf-figure-missing">'
        f'<div class="cf-image-missing">'
        f'<span class="cf-image-missing-icon" aria-hidden="true"></span>'
        f'<span class="cf-visually-hidden">Image not available locally: </span>'
        f'<span class="cf-image-missing-name">{_esc(name)}</span>'
        f'<span class="cf-image-missing-note">Not mirrored locally</span>'
        f'{link_html}</div>{caption_html}</figure>'
    )


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

def _convert_links(html, context):
    """Resolve ``ac:link`` forms and harden plain ``<a>`` elements."""

    def replace_ac_link(match):
        attrs = match.group(1) or ''
        block = match.group(0)

        body_match = re.search(r'<ac:link-body\s*>(.*?)</ac:link-body>', block,
                               flags=re.DOTALL | re.IGNORECASE)
        plain_match = re.search(r'<ac:plain-text-link-body\s*>\s*(?:<!\[CDATA\[)?(.*?)'
                                r'(?:\]\]>)?\s*</ac:plain-text-link-body>',
                                block, flags=re.DOTALL | re.IGNORECASE)
        label_html = ''
        if body_match:
            label_html = body_match.group(1)
        elif plain_match:
            label_html = _esc(plain_match.group(1))

        anchor_match = re.search(r'ac:anchor="([^"]*)"', attrs, re.IGNORECASE)
        anchor = anchor_match.group(1) if anchor_match else ''

        # Attachment link
        att = re.search(r'<ri:attachment\s+[^>]*ri:filename="([^"]+)"', block, re.IGNORECASE)
        if att:
            filename = html_lib.unescape(att.group(1))
            url = context.attachment_url(filename)
            label = label_html or _esc(filename)
            if url:
                return (f'<a class="cf-attachment-link" href="{_esc_attr(url)}">'
                        f'{label}</a>')
            return f'<span class="cf-page-ref">{label}</span>'

        # Internal page link
        page = re.search(r'<ri:page\s+([^>]*)/>', block, re.IGNORECASE)
        if page:
            page_attrs = page.group(1)
            title_match = re.search(r'ri:content-title="([^"]*)"', page_attrs, re.IGNORECASE)
            space_match = re.search(r'ri:space-key="([^"]*)"', page_attrs, re.IGNORECASE)
            title = html_lib.unescape(title_match.group(1)) if title_match else ''
            space = html_lib.unescape(space_match.group(1)) if space_match else ''
            label = label_html or _esc(title) or 'Linked page'

            local = context.local_page_url(space, title) if title else None
            fragment = f'#{_slugify(anchor)}' if anchor else ''
            if local:
                return f'<a class="cf-page-link" href="{_esc_attr(local + fragment)}">{label}</a>'

            remote = context.confluence_page_url(space, title) if title else None
            if remote:
                return (f'<a class="cf-page-link cf-page-link-remote" '
                        f'href="{_esc_attr(remote)}" target="_blank" rel="noopener noreferrer">'
                        f'{label}<span class="cf-visually-hidden"> '
                        f'(in Confluence, opens in a new tab)</span></a>')
            return (f'<span class="cf-page-ref" '
                    f'title="Linked Confluence page is not in the local mirror">{label}</span>')

        # Same-page anchor link
        if anchor:
            label = label_html or _esc(anchor)
            return f'<a class="cf-anchor-link" href="#{_esc_attr(_slugify(anchor))}">{label}</a>'

        # Blog post / space / unknown resource: keep the label, claim no target.
        if label_html:
            return f'<span class="cf-page-ref">{label_html}</span>'
        return ''

    html = re.sub(r'<ac:link\b([^>]*)>.*?</ac:link>', replace_ac_link, html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<ac:link\b([^>]*)/>', replace_ac_link, html, flags=re.IGNORECASE)

    return _harden_anchors(html, context)


def _harden_anchors(html, context):
    """Drop unsafe hrefs and mark external links as opening in a new tab."""

    def replace(match):
        attrs = match.group(1)
        href_match = re.search(r'href="([^"]*)"', attrs, re.IGNORECASE)
        if not href_match:
            return f'<a{attrs}>'
        href = href_match.group(1)

        if not _is_safe_url(href):
            # Keep the link text, discard the unsafe destination.
            return '<span class="cf-unsafe-link" title="Link removed: unsupported URL scheme">'

        unescaped = html_lib.unescape(href).strip()
        is_external = unescaped.lower().startswith(('http://', 'https://'))
        if is_external and context.site_base_url:
            base = context.site_base_url.rstrip('/').lower()
            if unescaped.lower().startswith(base):
                is_external = False

        if is_external and 'target=' not in attrs.lower():
            return (f'<a{attrs} class="cf-external-link" target="_blank" '
                    f'rel="noopener noreferrer">')
        return f'<a{attrs}>'

    html = re.sub(r'<a\b([^>]*)>', replace, html, flags=re.IGNORECASE)
    # Balance any <a> replaced by a <span> above.
    if 'cf-unsafe-link' in html:
        html = _rebalance_unsafe_links(html)
    return html


def _rebalance_unsafe_links(html):
    """Close ``cf-unsafe-link`` spans that replaced an opening ``<a>``."""
    out = []
    pending = []
    token_re = re.compile(r'<span class="cf-unsafe-link"[^>]*>|</a>', re.IGNORECASE)
    pos = 0
    for match in token_re.finditer(html):
        out.append(html[pos:match.start()])
        token = match.group(0)
        if token.lower().startswith('<span'):
            pending.append(True)
            out.append(token)
        else:
            if pending:
                pending.pop()
                out.append('</span>')
            else:
                out.append('</a>')
        pos = match.end()
    out.append(html[pos:])
    return ''.join(out)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# Confluence layout section type -> column count.
LAYOUT_COLUMNS = {
    'single': 1,
    'fixed-width': 1,
    'two_equal': 2,
    'two_left_sidebar': 2,
    'two_right_sidebar': 2,
    'three_equal': 3,
    'three_with_sidebars': 3,
}


def _convert_layout(html):
    """Turn Confluence column layouts into a responsive grid.

    Single-column sections are unwrapped so they add no nesting; multi-column
    sections collapse to one column on narrow screens (styling in index.css).
    """

    def replace_section(match):
        section_type = (match.group(1) or '').strip().lower()
        body = match.group(2)
        columns = LAYOUT_COLUMNS.get(section_type, 1)

        cells = re.findall(r'<ac:layout-cell\s*>(.*?)</ac:layout-cell>',
                           body, flags=re.DOTALL | re.IGNORECASE)
        if not cells:
            cells = re.findall(r'<ac:layout-cell\b[^>]*>(.*?)</ac:layout-cell>',
                               body, flags=re.DOTALL | re.IGNORECASE)

        if columns <= 1 or len(cells) <= 1:
            if cells:
                return ''.join(cells)
            return re.sub(r'</?ac:layout-cell\b[^>]*>', '', body, flags=re.IGNORECASE)

        inner = ''.join(f'<div class="cf-col">{cell}</div>' for cell in cells)
        return f'<div class="cf-columns cf-columns-{min(columns, 3)}">{inner}</div>'

    html = re.sub(
        r'<ac:layout-section\b[^>]*?ac:type="([^"]+)"[^>]*>(.*?)</ac:layout-section>',
        replace_section, html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(r'</?ac:layout\b[^>]*>', '', html, flags=re.IGNORECASE)
    return html


# ---------------------------------------------------------------------------
# Safety, tables, headings, tidy-up
# ---------------------------------------------------------------------------

# Elements whose entire subtree is discarded: nothing in a mirrored runbook body
# legitimately contains these, and each can execute, phone home, or overlay the
# application chrome.
_ACTIVE_ELEMENTS_WITH_CONTENT = ('script', 'style', 'svg', 'math', 'iframe',
                                 'object', 'embed', 'applet', 'template',
                                 'noscript', 'audio', 'video', 'canvas')

# Elements removed while keeping their inner text: a legacy body occasionally
# wraps real prose in form markup, and that prose must survive.
_ACTIVE_ELEMENTS_UNWRAP = ('form', 'button', 'select', 'option', 'textarea',
                           'label', 'fieldset', 'legend')

# Void elements that carry no text worth keeping.
_ACTIVE_VOID_ELEMENTS = ('input', 'link', 'meta', 'base', 'source', 'track',
                         'param')


def _strip_active_content(html):
    """Remove anything executable or embeddable from the imported body.

    The frontend applies an independent allowlist as well
    (frontend/src/components/reader/sanitizeArticle.js). This pass exists because
    the rendered HTML is also returned by the API, so the server must not hand
    out markup it would not be willing to render itself.

    Runs after code bodies have been escaped, so a ``<script>`` *inside* a code
    block is already ``&lt;script&gt;`` and is correctly left alone.
    """
    for tag in _ACTIVE_ELEMENTS_WITH_CONTENT:
        html = re.sub(rf'<{tag}\b[^>]*>.*?</{tag}\s*>', '', html,
                      flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(rf'<{tag}\b[^>]*/?>', '', html, flags=re.IGNORECASE)

    for tag in _ACTIVE_ELEMENTS_UNWRAP:
        html = re.sub(rf'</?{tag}\b[^>]*/?>', '', html, flags=re.IGNORECASE)

    for tag in _ACTIVE_VOID_ELEMENTS:
        html = re.sub(rf'<{tag}\b[^>]*/?>', '', html, flags=re.IGNORECASE)

    # Event handlers in any quoting style and any casing, including unquoted.
    html = re.sub(r'''\son[a-z]+\s*=\s*"[^"]*"''', '', html, flags=re.IGNORECASE)
    html = re.sub(r"""\son[a-z]+\s*=\s*'[^']*'""", '', html, flags=re.IGNORECASE)
    html = re.sub(r'''\son[a-z]+\s*=\s*[^\s>]+''', '', html, flags=re.IGNORECASE)

    # Attributes that fetch or submit to somewhere the reader did not choose.
    for attr in ('srcset', 'ping', 'formaction', 'background', 'xlink:href'):
        html = re.sub(rf'''\s{re.escape(attr)}\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)''',
                      '', html, flags=re.IGNORECASE)

    return html


# Inline declarations the reader keeps. Authored colours are dropped because they
# were chosen for Confluence's light canvas and become unreadable here; the
# highlight *meaning* survives via Confluence's own data-highlight-colour
# attribute, which the stylesheet maps to theme-aware tints.
SAFE_STYLE_PROPERTIES = ('text-align', 'vertical-align', 'width', 'min-width',
                         'max-width', 'font-weight', 'font-style')


def _sanitize_inline_styles(html):
    """Keep only layout-safe inline style declarations."""

    def replace(match):
        declarations = match.group(1)
        kept = []
        for declaration in declarations.split(';'):
            if ':' not in declaration:
                continue
            prop = declaration.split(':', 1)[0].strip().lower()
            value = declaration.split(':', 1)[1]
            if prop not in SAFE_STYLE_PROPERTIES:
                continue
            if 'url(' in value.lower() or 'expression' in value.lower():
                continue
            kept.append(f'{prop}:{value.strip()}')
        if not kept:
            return ''
        return f' style="{_esc_attr("; ".join(kept))}"'

    return re.sub(r'\s*style="([^"]*)"', replace, html, flags=re.IGNORECASE)


def _wrap_tables(html):
    """Put every table in its own labelled, keyboard-reachable scroll container.

    Component-level overflow keeps a wide table from forcing page-level
    horizontal scrolling, and ``tabindex="0"`` makes the scrollable region
    reachable without a mouse.
    """
    if '<table' not in html.lower():
        return html

    out = []
    pos = 0
    depth = 0
    token_re = re.compile(r'<table\b[^>]*>|</table\s*>', re.IGNORECASE)

    for match in token_re.finditer(html):
        token = match.group(0)
        out.append(html[pos:match.start()])
        if token.lower().startswith('<table'):
            if depth == 0:
                out.append('<div class="cf-table-wrap" role="region" '
                           'aria-label="Table, scrollable" tabindex="0">')
            depth += 1
            out.append(token)
        else:
            out.append(token)
            depth = max(0, depth - 1)
            if depth == 0:
                out.append('</div>')
        pos = match.end()

    out.append(html[pos:])
    return ''.join(out)


def _normalize_headings(html):
    """Give every heading a stable anchor id and keep one page-level ``h1``.

    Imported bodies sometimes contain their own ``h1`` (127 pages in this mirror).
    The page title is the only ``h1`` in the reader, so when a body ``h1`` exists
    every heading is demoted one level. Text, order, and relative hierarchy are
    unchanged; an ``h6`` stays an ``h6`` because HTML has no deeper level.
    """
    has_body_h1 = re.search(r'<h1\b', html, re.IGNORECASE) is not None
    used_ids = set()

    def replace(match):
        level = int(match.group(1))
        attrs = match.group(2) or ''
        inner = match.group(3)

        target = min(level + 1, 6) if has_body_h1 else level

        # Match only a standalone `id` attribute. A plain \bid="..." also matches
        # inside Confluence's own `local-id="..."`, which corrupted the attribute.
        existing = re.search(r'(?:^|\s)id="([^"]*)"', attrs, re.IGNORECASE)
        if existing and existing.group(1).strip():
            anchor = existing.group(1).strip()
            attrs = re.sub(r'(?:^|\s)id="[^"]*"', '', attrs, flags=re.IGNORECASE)
        else:
            anchor = _slugify(inner)

        unique = anchor
        suffix = 2
        while unique in used_ids:
            unique = f'{anchor}-{suffix}'
            suffix += 1
        used_ids.add(unique)

        return (f'<h{target}{attrs} id="{_esc_attr(unique)}" '
                f'class="cf-heading">{inner}</h{target}>')

    return re.sub(r'<h([1-6])\b([^>]*)>(.*?)</h\1\s*>', replace, html,
                  flags=re.DOTALL | re.IGNORECASE)


def _drop_empty_paragraphs(html):
    """Remove paragraphs that carry no content.

    These are editor artefacts (``<p />``, ``<p>&nbsp;</p>``), not authored text,
    and they add phantom vertical gaps between sections.
    """
    html = re.sub(r'<p\b[^>]*/>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<p\b[^>]*>(?:\s|&nbsp;|\u00a0|<br\s*/?>)*</p>', '', html,
                  flags=re.IGNORECASE)
    return html


# ---------------------------------------------------------------------------
# User lookup
# ---------------------------------------------------------------------------

def build_user_lookup(data_dir: str) -> dict:
    """Build an account-id -> display name map from stored page data.

    Strategy: scan all page.json files and their content.html to associate
    account IDs with known author names. When a page's created_by or
    updated_by appears as a mention, we can map the account ID.

    NOTE: this association is heuristic — it maps every account id found on a
    page to that page's author, so a mention of someone other than the author can
    resolve to the wrong name. It is preserved here unchanged because changing it
    is a data-accuracy decision outside the reader redesign; unresolved ids now
    render as "@Unknown user" rather than a guess.
    """
    import json
    from pathlib import Path

    lookup = {}
    spaces_dir = Path(data_dir) / 'spaces'
    if not spaces_dir.exists():
        return lookup

    # First pass: collect all known names from page metadata
    name_set = set()
    page_dirs = []
    for space_dir in spaces_dir.iterdir():
        if not space_dir.is_dir():
            continue
        for subdir in ('pages', 'blogposts'):
            pages_dir = space_dir / subdir
            if not pages_dir.exists():
                continue
            for page_dir in pages_dir.iterdir():
                page_json = page_dir / 'page.json'
                if page_json.exists():
                    try:
                        data = json.loads(page_json.read_text(encoding='utf-8'))
                        for field in ('created_by', 'updated_by'):
                            name = data.get(field)
                            if name:
                                name_set.add(name)
                        page_dirs.append((page_dir, data))
                    except Exception:
                        pass

    # Second pass: for pages where author is a mention, map account IDs
    for page_dir, data in page_dirs:
        html_path = page_dir / 'content.html'
        if not html_path.exists():
            continue
        try:
            content = html_path.read_text(encoding='utf-8')
        except Exception:
            continue

        # Extract all account IDs from this page
        account_ids = re.findall(r'ri:account-id="([^"]+)"', content)
        if not account_ids:
            continue

        # Map author names to account IDs found on their own pages
        for field in ('created_by', 'updated_by'):
            name = data.get(field)
            if name and name in name_set:
                for aid in account_ids:
                    if aid not in lookup:
                        lookup[aid] = name

    logger.info('User lookup built: %d account IDs mapped', len(lookup))
    return lookup
