"""
Confluence Storage Format parser with Markdown and HTML output.

Converts Confluence Cloud/Server storage format (XHTML with ac:/ri: namespaced
elements) into clean Markdown or self-contained HTML.

Designed as a talon-tools integration module:
- Auto-resolves JIRA issue references and user mentions via callbacks
- Accepts raw page content (from confluence_get_page) or XHTML body directly
- Zero external dependencies (stdlib only)

Usage:
    from confluence_parse import parse, parse_page

    # Markdown output (default)
    md = parse(xhtml_body)
    md = parse_page(raw_page_content)

    # HTML output
    html = parse(xhtml_body, fmt='html', title='My Page')
    html = parse_page(raw_page_content, fmt='html')

    # With resolvers
    md = parse(xhtml_body, user_resolver=lookup_user, jira_resolver=lookup_jira)
"""

from __future__ import annotations

import re
import sys
from html import escape, unescape
from html.parser import HTMLParser
from typing import Optional, Callable

# Type aliases for resolver callbacks
UserResolver = Callable[[str], Optional[str]]          # account_id -> display_name
JiraResolver = Callable[[str], Optional[tuple[str, str, str]]]  # key -> (title, status, url)


# ======================================================================
# Public API
# ======================================================================

def parse(xhtml: str, *,
          fmt: str = 'md',
          title: str = '',
          jira_base_url: str = '',
          user_resolver: Optional[UserResolver] = None,
          jira_resolver: Optional[JiraResolver] = None) -> str:
    """
    Parse Confluence storage format XHTML body.

    Args:
        xhtml: Raw Confluence storage format body string.
        fmt: Output format - 'md' (Markdown) or 'html' (self-contained HTML page).
        title: Page title (used as heading in both formats).
        jira_base_url: Base URL for JIRA links (e.g. 'https://nice-actimize.atlassian.net').
        user_resolver: callable(account_id) -> display_name or None.
        jira_resolver: callable(key) -> (title, status, url) or None.

    Returns:
        Formatted string (Markdown or complete HTML document).
    """
    if fmt == 'html':
        return _render_html(xhtml, title=title, jira_base_url=jira_base_url,
                            user_resolver=user_resolver, jira_resolver=jira_resolver)
    else:
        return _render_md(xhtml, user_resolver=user_resolver, jira_resolver=jira_resolver,
                          title=title)


def parse_page(raw_content: str, *,
               fmt: str = 'md',
               jira_base_url: str = '',
               user_resolver: Optional[UserResolver] = None,
               jira_resolver: Optional[JiraResolver] = None) -> str:
    """
    Parse a full page response (with metadata header) from confluence_get_page.

    Expects format:
        # Title
        **ID:** ... | **Space:** ... | **Version:** ...
        <xhtml body>

    Args:
        raw_content: Full page content string from confluence_get_page tool.
        fmt: Output format - 'md' or 'html'.
        jira_base_url: Base URL for JIRA links.
        user_resolver: callable(account_id) -> display_name or None.
        jira_resolver: callable(key) -> (title, status, url) or None.

    Returns:
        Formatted string.
    """
    title, body = _split_page_header(raw_content)
    return parse(body, fmt=fmt, title=title, jira_base_url=jira_base_url,
                 user_resolver=user_resolver, jira_resolver=jira_resolver)


def extract_refs(xhtml: str) -> dict[str, set[str]]:
    """
    Pre-scan XHTML for JIRA keys and user account IDs (for batch resolution).

    Returns:
        {'jira_keys': set(...), 'user_ids': set(...)}
    """
    jira_keys = set(re.findall(r'<ac:parameter ac:name="key">([^<]+)</ac:parameter>', xhtml))
    user_ids = set(re.findall(r'ri:account-id="([^"]+)"', xhtml))
    return {'jira_keys': jira_keys, 'user_ids': user_ids}


# ======================================================================
# Internal: Shared utilities
# ======================================================================

def _split_page_header(raw_content: str) -> tuple[str, str]:
    """Extract title and body from a page response with metadata header."""
    lines = raw_content.split('\n')
    title = ''
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith('# '):
            title = line[2:].strip()
            body_start = i + 1
            continue
        if line.startswith('**ID:**'):
            body_start = i + 1
            continue
        if line.strip():
            body_start = i
            break

    body = '\n'.join(lines[body_start:])
    return title, body


def _normalize_xhtml(xhtml: str) -> str:
    """Normalize self-closing tags that HTMLParser can't handle."""
    xhtml = re.sub(r'<(ri:\w+)([^>]*)/>', r'<\1\2></\1>', xhtml)
    xhtml = re.sub(r'<(ac:emoticon)([^>]*)/>', r'<\1\2></\1>', xhtml)
    return xhtml


# ======================================================================
# Markdown Renderer
# ======================================================================

def _render_md(xhtml: str, *, user_resolver=None, jira_resolver=None, title: str = '') -> str:
    parser = _MdParser(user_resolver=user_resolver, jira_resolver=jira_resolver)
    md = parser.parse(xhtml)
    if title:
        return f'# {title}\n\n{md}'
    return md


class _MdParser(HTMLParser):
    """Event-driven parser: Confluence storage format → Markdown."""

    def __init__(self, user_resolver=None, jira_resolver=None):
        super().__init__(convert_charrefs=True)
        self._output: list[str] = []
        self._stack: list[str] = []
        self._table_stack: list[_Table] = []
        self._table: Optional[_Table] = None
        self._list_stack: list[str] = []
        self._list_counters: list[int] = []
        self._macro_name: str = ""
        self._macro_params: dict[str, str] = {}
        self._in_code_block = False
        self._code_buffer: list[str] = []
        self._suppress = False
        self._task_status: str = ""
        self._inline_buffer: list[str] = []
        self._in_table_cell = False
        self._cell_depth = 0
        self._heading_level = 0
        self._user_resolver = user_resolver
        self._jira_resolver = jira_resolver

    def parse(self, html: str) -> str:
        html = _normalize_xhtml(html)
        self.feed(html)
        self.close()
        return self._finalize()

    # --- HTMLParser overrides ---

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        attr = dict(attrs)
        self._stack.append(tag)

        m = re.match(r'^h([1-6])$', tag)
        if m:
            self._heading_level = int(m.group(1))
            self._inline_buffer = []
            return

        if tag == 'p':
            return

        if tag == 'strong' or tag == 'b':
            self._emit_inline('**')
            return
        if tag == 'em' or tag == 'i':
            self._emit_inline('*')
            return
        if tag == 'u':
            self._emit_inline('__')
            return
        if tag == 'code':
            self._emit_inline('`')
            return
        if tag == 'del' or tag == 's':
            self._emit_inline('~~')
            return
        if tag == 'sub':
            self._emit_inline('~')
            return
        if tag == 'sup':
            self._emit_inline('^')
            return

        if tag == 'a':
            href = attr.get('href', '')
            self._emit_inline('[')
            self._stack_meta('a_href', href)
            return
        if tag == 'ac:link':
            return
        if tag == 'ri:page':
            title = attr.get('ri:content-title', '')
            self._stack_meta('link_page', title)
            return
        if tag == 'ri:user':
            account = attr.get('ri:account-id', attr.get('ri:userkey', ''))
            self._stack_meta('link_user', account)
            return
        if tag == 'ri:url':
            url = attr.get('ri:value', '')
            self._stack_meta('link_url', url)
            return

        if tag == 'ac:image':
            return
        if tag == 'ri:attachment':
            filename = attr.get('ri:filename', '')
            self._emit_inline(f'![{filename}]({filename})')
            return

        if tag == 'table':
            if self._table is not None:
                self._table_stack.append(self._table)
            self._table = _Table()
            return
        if tag == 'tr':
            if self._table:
                self._table.new_row()
            return
        if tag in ('th', 'td'):
            self._in_table_cell = True
            self._cell_depth += 1
            self._inline_buffer = []
            if self._table:
                self._table.mark_header(tag == 'th')
            return
        if tag in ('colgroup', 'col', 'thead', 'tbody', 'tfoot'):
            return

        if tag in ('ul', 'ol'):
            self._list_stack.append(tag)
            self._list_counters.append(0)
            if self._in_table_cell:
                self._stack_meta('cell_list_depth', str(len(self._list_stack)))
            return
        if tag == 'li':
            if self._list_counters:
                self._list_counters[-1] += 1
            if not self._in_table_cell and not self._heading_level:
                text = ''.join(self._inline_buffer).strip()
                if text:
                    self._emit(text + '\n')
            self._inline_buffer = []
            return

        if tag == 'ac:structured-macro':
            self._macro_name = attr.get('ac:name', '')
            self._macro_params = {}
            return
        if tag == 'ac:parameter':
            name = attr.get('ac:name', '')
            self._stack_meta('param_name', name)
            self._suppress = True
            self._inline_buffer = []
            return
        if tag == 'ac:plain-text-body':
            self._in_code_block = True
            self._code_buffer = []
            return
        if tag == 'ac:rich-text-body':
            return

        if tag == 'ac:task-list':
            return
        if tag == 'ac:task':
            self._task_status = ''
            return
        if tag == 'ac:task-status':
            self._inline_buffer = []
            return
        if tag == 'ac:task-body':
            self._inline_buffer = []
            return

        if tag == 'ac:emoticon':
            name = attr.get('ac:name', '')
            emoji_map = {
                'tick': '✓', 'cross': '✗', 'warning': '⚠️',
                'info': 'ℹ️', 'plus': '➕', 'minus': '➖',
                'question': '❓', 'light-on': '💡', 'star_yellow': '⭐',
                'thumbs-up': '👍', 'thumbs-down': '👎',
            }
            self._emit_inline(emoji_map.get(name, f':{name}:'))
            return

        if tag == 'br':
            if self._in_table_cell:
                self._emit_inline('<br>')
            else:
                self._emit_inline('\n')
            return

        if tag == 'hr':
            self._emit('\n---\n')
            return

    def handle_endtag(self, tag: str):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

        m = re.match(r'^h([1-6])$', tag)
        if m:
            text = ''.join(self._inline_buffer).strip()
            prefix = '#' * self._heading_level
            self._emit(f'\n{prefix} {text}\n')
            self._heading_level = 0
            self._inline_buffer = []
            return

        if tag == 'p':
            if self._in_table_cell:
                text = ''.join(self._inline_buffer).strip()
                if text and not text.endswith('<br>'):
                    self._inline_buffer.append('<br>')
                return
            if self._heading_level or self._suppress or self._list_stack:
                return
            text = ''.join(self._inline_buffer).strip()
            if text:
                self._emit(text + '\n')
            else:
                self._emit('\n')
            self._inline_buffer = []
            return

        if tag in ('strong', 'b'):
            self._emit_inline('**')
            return
        if tag in ('em', 'i'):
            self._emit_inline('*')
            return
        if tag == 'u':
            self._emit_inline('__')
            return
        if tag == 'code':
            self._emit_inline('`')
            return
        if tag in ('del', 's'):
            self._emit_inline('~~')
            return
        if tag == 'sub':
            self._emit_inline('~')
            return
        if tag == 'sup':
            self._emit_inline('^')
            return

        if tag == 'a':
            href = self._pop_meta('a_href', '')
            self._emit_inline(f']({href})')
            return
        if tag == 'ac:link':
            page = self._pop_meta('link_page', '')
            user = self._pop_meta('link_user', '')
            url = self._pop_meta('link_url', '')
            if user:
                display = None
                if self._user_resolver:
                    display = self._user_resolver(user)
                if display:
                    self._emit_inline(f'@{display}')
                else:
                    self._emit_inline(f'@user:{user[:8]}')
            elif page:
                self._emit_inline(f'[[{page}]]')
            elif url:
                self._emit_inline(f'[link]({url})')
            return

        if tag in ('th', 'td'):
            self._cell_depth -= 1
            if self._cell_depth <= 0:
                self._in_table_cell = False
                self._cell_depth = 0
            text = ''.join(self._inline_buffer).strip()
            text = re.sub(r'(<br>)+$', '', text).strip()
            if self._table:
                self._table.add_cell(text)
            self._inline_buffer = []
            return
        if tag == 'tr':
            return
        if tag == 'table':
            if self._table:
                rendered = self._table.render()
                if self._table_stack:
                    self._table = self._table_stack.pop()
                    if rendered:
                        self._inline_buffer.append('<br>' + rendered.replace('\n', '<br>'))
                else:
                    if rendered:
                        self._emit('\n' + rendered + '\n')
                    self._table = None
            return

        if tag in ('ul', 'ol'):
            if self._list_stack:
                self._list_stack.pop()
            if self._list_counters:
                self._list_counters.pop()
            if self._in_table_cell:
                self._pop_meta('cell_list_depth', '')
            elif not self._list_stack:
                self._emit('\n')
            return
        if tag == 'li':
            text = ''.join(self._inline_buffer).strip()
            if self._in_table_cell and self._table:
                num = self._list_counters[-1] if self._list_counters else 1
                if self._list_stack and self._list_stack[-1] == 'ol':
                    prefix = f'{num}.'
                else:
                    prefix = '•'
                self._inline_buffer = []
                separator = '<br>' if self._table.peek_cell() else ''
                self._table.append_to_cell(f'{separator}{prefix} {text}')
            else:
                indent = '  ' * (len(self._list_stack) - 1)
                if self._list_stack and self._list_stack[-1] == 'ol':
                    num = self._list_counters[-1] if self._list_counters else 1
                    self._emit(f'{indent}{num}. {text}\n')
                else:
                    self._emit(f'{indent}- {text}\n')
                self._inline_buffer = []
            return

        if tag == 'ac:parameter':
            self._suppress = False
            name = self._pop_meta('param_name', '')
            value = ''.join(self._inline_buffer).strip()
            self._macro_params[name] = value
            self._inline_buffer = []
            return
        if tag == 'ac:plain-text-body':
            self._in_code_block = False
            return
        if tag == 'ac:structured-macro':
            self._handle_macro_end()
            return

        if tag == 'ac:task-status':
            status = ''.join(self._inline_buffer).strip().lower()
            self._task_status = status
            self._inline_buffer = []
            return
        if tag == 'ac:task-body':
            text = ''.join(self._inline_buffer).strip()
            checkbox = '[x]' if self._task_status == 'complete' else '[ ]'
            self._emit(f'- {checkbox} {text}\n')
            self._inline_buffer = []
            return
        if tag == 'ac:task':
            return
        if tag == 'ac:task-list':
            self._emit('\n')
            return

    def handle_data(self, data: str):
        if self._in_code_block:
            self._code_buffer.append(data)
            return
        if self._suppress:
            self._inline_buffer.append(data)
            return
        self._emit_inline(data)

    def handle_entityref(self, name: str):
        self._emit_inline(unescape(f'&{name};'))

    def handle_charref(self, name: str):
        self._emit_inline(unescape(f'&#{name};'))

    # --- Internals ---

    def _emit(self, text: str):
        self._output.append(text)

    def _emit_inline(self, text: str):
        self._inline_buffer.append(text)

    def _stack_meta(self, key: str, value: str):
        if not hasattr(self, '_meta'):
            self._meta: dict[str, list[str]] = {}
        self._meta.setdefault(key, []).append(value)

    def _pop_meta(self, key: str, default: str = '') -> str:
        if hasattr(self, '_meta') and key in self._meta and self._meta[key]:
            return self._meta[key].pop()
        return default

    def _handle_macro_end(self):
        name = self._macro_name
        params = self._macro_params

        if name in ('code', 'noformat'):
            lang = params.get('language', params.get('lang', ''))
            code = ''.join(self._code_buffer).strip('\n')
            self._emit(f'\n```{lang}\n{code}\n```\n')
        elif name == 'info':
            body = ''.join(self._code_buffer).strip()
            if body:
                self._emit(f'\n> ℹ️ **Info:** {body}\n')
        elif name == 'warning':
            body = ''.join(self._code_buffer).strip()
            if body:
                self._emit(f'\n> ⚠️ **Warning:** {body}\n')
        elif name == 'note':
            body = ''.join(self._code_buffer).strip()
            if body:
                self._emit(f'\n> 📝 **Note:** {body}\n')
        elif name == 'tip':
            body = ''.join(self._code_buffer).strip()
            if body:
                self._emit(f'\n> 💡 **Tip:** {body}\n')
        elif name == 'expand':
            title = params.get('title', 'Details')
            self._emit(f'\n<details><summary>{title}</summary>\n')
        elif name == 'toc':
            self._emit('\n[TOC]\n')
        elif name == 'status':
            color = params.get('colour', params.get('color', ''))
            title = params.get('title', '')
            color_emoji = {
                'Green': '🟢', 'Red': '🔴', 'Yellow': '🟡',
                'Blue': '🔵', 'Grey': '⚪',
            }
            emoji = color_emoji.get(color, '⚪')
            self._emit_inline(f'{emoji} {title}')
        elif name == 'jira':
            key = params.get('key', '')
            resolved = None
            if self._jira_resolver:
                resolved = self._jira_resolver(key)
            if resolved:
                title, status, url = resolved
                self._emit_inline(f'[{key}: {title}]({url}) ({status})')
            else:
                self._emit_inline(f'[{key}]')
        elif name == 'anchor':
            pass
        elif name == 'panel':
            title = params.get('title', '')
            if title:
                self._emit(f'\n> **{title}**\n')

        self._macro_name = ''
        self._macro_params = {}
        self._code_buffer = []

    def _finalize(self) -> str:
        text = ''.join(self._output)
        text = text.replace('\xa0', ' ')
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


class _Table:
    """Accumulates table rows and renders as Markdown."""

    def __init__(self):
        self._rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._has_header = False
        self._header_row_idx: Optional[int] = None

    def new_row(self):
        if self._current_row:
            self._rows.append(self._current_row)
        self._current_row = []

    def mark_header(self, is_header: bool):
        if is_header and self._header_row_idx is None:
            self._has_header = True
            self._header_row_idx = len(self._rows)

    def add_cell(self, text: str):
        self._current_row.append(text)

    def append_to_cell(self, text: str):
        if self._current_row:
            self._current_row[-1] += text
        else:
            self._current_row.append(text)

    def peek_cell(self) -> str:
        if self._current_row:
            return self._current_row[-1]
        return ''

    def render(self) -> str:
        if self._current_row:
            self._rows.append(self._current_row)
            self._current_row = []

        if not self._rows:
            return ''

        # Filter out pure numbering columns
        if len(self._rows) > 1:
            first_col = [row[0] if row else '' for row in self._rows]
            if all(re.match(r'^\d*$', c) for c in first_col[1:]):
                if not first_col[0] or re.match(r'^\d*$', first_col[0]):
                    self._rows = [row[1:] for row in self._rows if row]

        if not self._rows:
            return ''

        max_cols = max(len(r) for r in self._rows)
        for row in self._rows:
            while len(row) < max_cols:
                row.append('')

        lines = []
        for i, row in enumerate(self._rows):
            escaped = [c.replace('|', '\\|').replace('\n', '<br>') for c in row]
            lines.append('| ' + ' | '.join(escaped) + ' |')
            if i == 0 and self._has_header:
                lines.append('| ' + ' | '.join(['---'] * max_cols) + ' |')

        if not self._has_header and len(lines) > 1:
            lines.insert(1, '| ' + ' | '.join(['---'] * max_cols) + ' |')

        return '\n'.join(lines)


# ======================================================================
# HTML Renderer
# ======================================================================

_CSS = """\
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
    max-width: 1100px;
    margin: 0 auto;
    padding: 2rem;
    line-height: 1.6;
    color: #172b4d;
}
h1, h2, h3, h4, h5, h6 { color: #172b4d; margin-top: 1.5em; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}
th, td {
    border: 1px solid #dfe1e6;
    padding: 8px 12px;
    text-align: left;
    vertical-align: top;
}
th { background: #f4f5f7; font-weight: 600; }
tr:nth-child(even) { background: #fafbfc; }
code {
    background: #f4f5f7;
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 0.9em;
}
pre {
    background: #f4f5f7;
    padding: 1em;
    border-radius: 4px;
    overflow-x: auto;
}
blockquote {
    border-left: 4px solid #0052cc;
    margin: 1em 0;
    padding: 0.5em 1em;
    background: #f4f5f7;
}
a { color: #0052cc; text-decoration: none; }
a:hover { text-decoration: underline; }
.status {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.85em;
    font-weight: 600;
}
.status-green { background: #e3fcef; color: #006644; }
.status-red { background: #ffebe6; color: #bf2600; }
.status-yellow { background: #fffae6; color: #ff8b00; }
.status-blue { background: #deebff; color: #0747a6; }
.status-grey { background: #f4f5f7; color: #505f79; }
.info-panel, .warning-panel, .note-panel, .tip-panel {
    border-radius: 4px;
    padding: 1em;
    margin: 1em 0;
}
.info-panel { background: #deebff; border-left: 4px solid #0052cc; }
.warning-panel { background: #fffae6; border-left: 4px solid #ff8b00; }
.note-panel { background: #eae6ff; border-left: 4px solid #6554c0; }
.tip-panel { background: #e3fcef; border-left: 4px solid #00875a; }
ul.task-list { list-style: none; padding-left: 0; }
ul.task-list li { padding: 4px 0; }
ul.task-list li::before { content: none; }
.task-checkbox { margin-right: 8px; }
.user-mention {
    background: #deebff;
    color: #0747a6;
    padding: 1px 4px;
    border-radius: 3px;
    font-weight: 500;
}
.jira-link {
    background: #f4f5f7;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
    font-size: 0.9em;
}
"""


def _render_html(xhtml: str, *, title: str = '', jira_base_url: str = '',
                 user_resolver=None, jira_resolver=None) -> str:
    converter = _HtmlParser(jira_base_url=jira_base_url,
                            user_resolver=user_resolver, jira_resolver=jira_resolver)
    body = converter.convert(xhtml)

    title_tag = escape(title) if title else 'Confluence Page'
    heading = f'<h1>{escape(title)}</h1>\n' if title else ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_tag}</title>
<style>
{_CSS}
</style>
</head>
<body>
{heading}{body}
</body>
</html>"""


class _HtmlParser(HTMLParser):
    """Converts Confluence storage format to clean HTML."""

    def __init__(self, jira_base_url: str = '', user_resolver=None, jira_resolver=None):
        super().__init__(convert_charrefs=True)
        self._output: list[str] = []
        self._stack: list[str] = []
        self._skip_depth = 0
        self._in_macro = False
        self._macro_name = ""
        self._macro_params: dict[str, str] = {}
        self._param_name = ""
        self._param_buffer: list[str] = []
        self._collecting_param = False
        self._code_buffer: list[str] = []
        self._in_code_body = False
        self._in_rich_body = False
        self._task_status = ""
        self._task_body_buffer: list[str] = []
        self._in_task_body = False
        self._in_task_status = False
        self._status_buffer: list[str] = []
        self._jira_base_url = jira_base_url
        self._user_resolver = user_resolver
        self._jira_resolver = jira_resolver

    def convert(self, xhtml: str) -> str:
        xhtml = _normalize_xhtml(xhtml)
        self.feed(xhtml)
        self.close()
        return ''.join(self._output)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        attr = dict(attrs)
        self._stack.append(tag)

        if tag == 'ac:structured-macro':
            self._in_macro = True
            self._macro_name = attr.get('ac:name', '')
            self._macro_params = {}
            return
        if tag == 'ac:parameter':
            self._param_name = attr.get('ac:name', '')
            self._collecting_param = True
            self._param_buffer = []
            return
        if tag == 'ac:plain-text-body':
            self._in_code_body = True
            self._code_buffer = []
            return
        if tag == 'ac:rich-text-body':
            self._in_rich_body = True
            if self._macro_name in ('info', 'warning', 'note', 'tip'):
                cls = f'{self._macro_name}-panel'
                self._output.append(f'<div class="{cls}">')
            elif self._macro_name == 'expand':
                title = self._macro_params.get('title', 'Click to expand')
                self._output.append(f'<details><summary>{escape(title)}</summary>')
            elif self._macro_name == 'panel':
                title = self._macro_params.get('title', '')
                self._output.append('<div class="info-panel">')
                if title:
                    self._output.append(f'<strong>{escape(title)}</strong><br>')
            return

        if tag == 'ac:task-list':
            self._output.append('<ul class="task-list">')
            return
        if tag == 'ac:task':
            self._task_status = ''
            return
        if tag == 'ac:task-status':
            self._in_task_status = True
            self._status_buffer = []
            return
        if tag == 'ac:task-body':
            self._in_task_body = True
            self._task_body_buffer = []
            return

        if tag == 'ac:link':
            return
        if tag == 'ri:page':
            title = attr.get('ri:content-title', '')
            self._output.append(f'<a href="#" title="Confluence: {escape(title)}">{escape(title)}</a>')
            return
        if tag == 'ri:user':
            account_id = attr.get('ri:account-id', attr.get('ri:userkey', ''))
            display_name = None
            if self._user_resolver and account_id:
                display_name = self._user_resolver(account_id)
            if display_name:
                self._output.append(
                    f'<span class="user-mention" title="{escape(account_id)}">'
                    f'@{escape(display_name)}</span>'
                )
            else:
                self._output.append(
                    f'<span class="user-mention" title="{escape(account_id)}">@user</span>'
                )
            return
        if tag == 'ri:url':
            url = attr.get('ri:value', '')
            self._output.append(f'<a href="{escape(url)}">')
            return
        if tag == 'ri:attachment':
            filename = attr.get('ri:filename', '')
            self._output.append(f'<img src="{escape(filename)}" alt="{escape(filename)}" />')
            return

        if tag == 'ac:image':
            return

        if tag == 'ac:emoticon':
            name = attr.get('ac:name', '')
            emoji_map = {
                'tick': '✓', 'cross': '✗', 'warning': '⚠️',
                'info': 'ℹ️', 'plus': '➕', 'minus': '➖',
                'question': '❓', 'light-on': '💡', 'star_yellow': '⭐',
                'thumbs-up': '👍', 'thumbs-down': '👎',
            }
            self._emit(emoji_map.get(name, f':{name}:'))
            return

        if tag.startswith('ac:') or tag.startswith('ri:'):
            return

        # Standard HTML passthrough with cleaned attributes
        clean_attrs = []
        for k, v in attrs:
            if k and not k.startswith('ac:') and k not in ('local-id', 'data-layout',
                                                            'data-table-width'):
                if k == 'class':
                    classes = (v or '').split()
                    classes = [c for c in classes if not c.startswith('SCXW')
                               and not c.startswith('BCX')]
                    if classes:
                        clean_attrs.append(f'class="{escape(" ".join(classes))}"')
                elif k == 'style':
                    clean_attrs.append(f'style="{escape(v or "")}"')
                elif k == 'href':
                    clean_attrs.append(f'href="{escape(v or "")}"')
                elif k == 'colspan':
                    clean_attrs.append(f'colspan="{escape(v or "")}"')
                elif k == 'rowspan':
                    clean_attrs.append(f'rowspan="{escape(v or "")}"')

        if tag in ('th', 'td') and 'numberingColumn' in (attr.get('class', '')):
            self._skip_depth = 1
            return

        attr_str = ' ' + ' '.join(clean_attrs) if clean_attrs else ''
        self._output.append(f'<{tag}{attr_str}>')

    def handle_endtag(self, tag: str):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

        if self._skip_depth > 0:
            if tag in ('th', 'td'):
                self._skip_depth = 0
            return

        if tag == 'ac:parameter':
            self._collecting_param = False
            self._macro_params[self._param_name] = ''.join(self._param_buffer).strip()
            return
        if tag == 'ac:plain-text-body':
            self._in_code_body = False
            return
        if tag == 'ac:rich-text-body':
            self._in_rich_body = False
            if self._macro_name in ('info', 'warning', 'note', 'tip', 'panel'):
                self._output.append('</div>')
            elif self._macro_name == 'expand':
                self._output.append('</details>')
            return
        if tag == 'ac:structured-macro':
            self._handle_macro_end()
            self._in_macro = False
            return

        if tag == 'ac:task-list':
            self._output.append('</ul>')
            return
        if tag == 'ac:task-status':
            self._in_task_status = False
            self._task_status = ''.join(self._status_buffer).strip().lower()
            return
        if tag == 'ac:task-body':
            self._in_task_body = False
            checked = ' checked' if self._task_status == 'complete' else ''
            body = ''.join(self._task_body_buffer)
            self._output.append(
                f'<li><input type="checkbox" class="task-checkbox" disabled{checked}>{body}</li>'
            )
            return
        if tag == 'ac:task':
            return

        if tag == 'ac:link':
            return
        if tag == 'ri:url':
            self._output.append('</a>')
            return

        if tag.startswith('ac:') or tag.startswith('ri:'):
            return

        if self._skip_depth == 0:
            self._output.append(f'</{tag}>')

    def handle_data(self, data: str):
        if self._skip_depth > 0:
            return
        if self._collecting_param:
            self._param_buffer.append(data)
            return
        if self._in_code_body:
            self._code_buffer.append(data)
            return
        if self._in_task_status:
            self._status_buffer.append(data)
            return
        if self._in_task_body:
            self._task_body_buffer.append(data)
            return
        data = data.replace('\xa0', ' ')
        self._output.append(data)

    def handle_entityref(self, name: str):
        char = unescape(f'&{name};')
        if char == '\xa0':
            char = ' '
        self._emit(char)

    def handle_charref(self, name: str):
        char = unescape(f'&#{name};')
        if char == '\xa0':
            char = ' '
        self._emit(char)

    def _emit(self, text: str):
        if self._skip_depth > 0:
            return
        if self._collecting_param:
            self._param_buffer.append(text)
        elif self._in_code_body:
            self._code_buffer.append(text)
        elif self._in_task_status:
            self._status_buffer.append(text)
        elif self._in_task_body:
            self._task_body_buffer.append(text)
        else:
            self._output.append(text)

    def _handle_macro_end(self):
        name = self._macro_name
        params = self._macro_params

        if name in ('code', 'noformat'):
            lang = params.get('language', params.get('lang', ''))
            code = escape(''.join(self._code_buffer))
            lang_attr = f' data-language="{escape(lang)}"' if lang else ''
            self._output.append(f'<pre{lang_attr}><code>{code}</code></pre>')
        elif name == 'toc':
            self._output.append('<nav class="toc"><em>[Table of Contents]</em></nav>')
        elif name == 'status':
            color = params.get('colour', params.get('color', 'grey')).lower()
            title = params.get('title', '')
            self._output.append(
                f'<span class="status status-{color}">{escape(title)}</span>'
            )
        elif name == 'jira':
            key = params.get('key', '')
            jira_info = None
            if self._jira_resolver and key:
                jira_info = self._jira_resolver(key)
            if jira_info:
                title, status, url = jira_info
                status_cls = 'status-green' if status.lower() == 'done' else (
                    'status-blue' if status.lower() in ('in progress', 'ready for review') else 'status-grey'
                )
                self._output.append(
                    f'<a href="{escape(url)}" class="jira-link" title="{escape(title)}">{escape(key)}</a>'
                    f' <span class="status {status_cls}">{escape(status)}</span>'
                )
            elif self._jira_base_url and key:
                url = f'{self._jira_base_url}/browse/{key}'
                self._output.append(f'<a href="{escape(url)}" class="jira-link">{escape(key)}</a>')
            else:
                self._output.append(f'<code>[{escape(key)}]</code>')
        elif name == 'anchor':
            anchor_name = params.get('', params.get('0', ''))
            self._output.append(f'<a id="{escape(anchor_name)}"></a>')
        elif name in ('info', 'warning', 'note', 'tip', 'panel', 'expand'):
            pass  # handled by rich-text-body

        self._macro_name = ''
        self._macro_params = {}
        self._code_buffer = []


# ======================================================================
# CLI (for standalone testing)
# ======================================================================
