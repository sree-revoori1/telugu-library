"""Generating the static site.

Static on purpose. A parsing reader needs no server: the analysis is the same every
time, so it is computed once at build time and baked into the HTML. That means the whole
library hosts free on GitHub Pages, works offline, and cannot go down — which for a
reference work on a literature with few digital resources matters more than any dynamic
feature.

The word panel is the one piece of interactivity, and it is a few lines of vanilla
JavaScript reading `data-` attributes already in the markup. No framework, no build
step, no fonts to download — the reader's own Telugu font renders it.

One design decision worth stating. A token whose analysis failed is rendered as plain
text with no underline and no panel, rather than as a clickable word with an empty
gloss. Classical text runs well under half analysed, and a reader who clicks a word
expecting a gloss and gets nothing learns to distrust the ones that do have glosses.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .reader import Document
from .wikisource import LICENCE, LICENCE_URL

CSS = """
:root {
  --ink: #1a1a1a; --dim: #6b6b6b; --rule: #e0ddd6; --bg: #fdfcfa;
  --link: #7a4b2a; --panel: #f4f1ea; --known: #b8860b;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.75 Georgia, 'Noto Serif Telugu', serif;
}
.wrap { max-width: 46rem; margin: 0 auto; padding: 2rem 1.25rem 6rem; }
header { border-bottom: 1px solid var(--rule); margin-bottom: 2rem; }
header a { color: var(--ink); text-decoration: none; }
h1 { font-size: 1.6rem; line-height: 1.3; margin: 0 0 .4rem; font-weight: normal; }
h2 { font-size: 1.1rem; margin: 2.5rem 0 .75rem; font-weight: normal; color: var(--dim); }
.sub { color: var(--dim); font-size: .85rem; margin: 0 0 1.25rem; }
a { color: var(--link); }
/* Verse: preserve the line as the poet set it. */
.line { white-space: pre-wrap; margin: 0; }
.line.verse { padding-left: 1.5rem; }
.marker { color: var(--dim); font-size: .8rem; }
.vnum { color: var(--dim); font-size: .75rem; }
.stanza { margin: 0 0 1.4rem; }
/* An analysed token is clickable; an unanalysed one is inert and looks it. */
.w {
  cursor: pointer; border-bottom: 1px dotted var(--known);
}
.w:hover { background: #f7e9c9; }
.gap { color: inherit; }
#panel {
  position: fixed; left: 0; right: 0; bottom: 0; background: var(--panel);
  border-top: 1px solid var(--rule); padding: .9rem 1.25rem;
  display: none; font-size: .9rem;
}
#panel.on { display: block; }
#panel .surface { font-size: 1.2rem; }
#panel .lemma { color: var(--link); }
#panel .tag { color: var(--dim); font-family: ui-monospace, monospace; font-size: .8rem; }
#panel .alt { color: var(--dim); font-size: .8rem; }
#panel .close { float: right; cursor: pointer; color: var(--dim); }
ul.works { list-style: none; padding: 0; }
ul.works li { padding: .35rem 0; border-bottom: 1px solid var(--rule); }
.genre-grid { display: grid; gap: .5rem; }
.count { color: var(--dim); font-size: .8rem; }
footer {
  margin-top: 4rem; padding-top: 1rem; border-top: 1px solid var(--rule);
  color: var(--dim); font-size: .8rem;
}
"""

PANEL_JS = """
(function () {
  var panel = document.getElementById('panel');
  if (!panel) return;
  document.addEventListener('click', function (e) {
    var w = e.target.closest ? e.target.closest('.w') : null;
    if (!w) { return; }
    var alts = w.dataset.alt ? JSON.parse(w.dataset.alt) : [];
    var html = '<span class="close">close</span>'
      + '<span class="surface">' + w.textContent + '</span> &nbsp; '
      + '<span class="lemma">' + w.dataset.lemma + '</span> &nbsp; '
      + '<span class="tag">' + w.dataset.tag + '</span>';
    if (alts.length) {
      html += '<div class="alt">also: ' + alts.map(function (a) {
        return a[0] + ' ' + a[1];
      }).join(' &middot; ') + '</div>';
    }
    panel.innerHTML = html;
    panel.classList.add('on');
  });
  panel.addEventListener('click', function (e) {
    if (e.target.classList.contains('close')) panel.classList.remove('on');
  });
})();
"""


def _page(title: str, body: str, depth: int = 0) -> str:
    """One HTML page. `depth` sets how far back the root is, for relative links."""
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="te">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
<body>
<div class="wrap">
<header><h1><a href="{up}index.html">తెలుగు గ్రంథాలయం</a></h1>
<p class="sub">A parsing reader for Telugu literature</p></header>
{body}
<footer>
Texts from <a href="https://te.wikisource.org">Telugu Wikisource</a>,
<a href="{LICENCE_URL}">{LICENCE}</a>.
Morphology by <a href="https://github.com/sree-revoori1/telugu-morph">telugu-morph</a>.
</footer>
</div>
<div id="panel"></div>
<script>{PANEL_JS}</script>
</body></html>
"""


def render_document(document: Document, depth: int = 1) -> str:
    """A text as a reading page, every analysed token clickable."""
    parts: list[str] = []
    breadcrumb = " › ".join(html.escape(p) for p in document.path)
    parts.append(f'<h2>{breadcrumb}</h2>')
    parts.append(f"<h1>{html.escape(document.title)}</h1>")
    parts.append(
        f'<p class="sub">{document.token_count:,} Telugu words · '
        f"{document.coverage:.0f}% with a morphological gloss · "
        f'<a href="{html.escape(document.url)}">source</a></p>'
    )

    parts.append('<div class="stanza">')
    for line in document.lines:
        if line.is_blank:
            parts.append("</div><div class=\"stanza\">")
            continue
        classes = "line verse" if line.marker else "line"
        rendered: list[str] = []
        for token in line.tokens:
            escaped = html.escape(token.surface)
            if not token.is_telugu:
                rendered.append(escaped)
            elif token.unanalysed:
                # Inert. See the module docstring: a clickable word with no gloss
                # teaches the reader to distrust the glosses that are there.
                rendered.append(f'<span class="gap">{escaped}</span>')
            else:
                alt = (
                    html.escape(json.dumps(token.alternatives, ensure_ascii=False))
                    if token.alternatives
                    else ""
                )
                rendered.append(
                    f'<span class="w" data-lemma="{html.escape(token.lemma or "")}"'
                    f' data-tag="{html.escape(token.tag or "")}"'
                    + (f' data-alt="{alt}"' if alt else "")
                    + f">{escaped}</span>"
                )
        parts.append(f'<p class="{classes}">' + "".join(rendered) + "</p>")
    parts.append("</div>")
    return _page(document.title, "\n".join(parts), depth=depth)


def render_index(genres: dict[str, list], descriptions: dict[str, str]) -> str:
    """The front page: genres, with counts."""
    parts = ['<div class="genre-grid">']
    for genre, works in sorted(genres.items(), key=lambda kv: -len(kv[1])):
        description = html.escape(descriptions.get(genre, ""))
        parts.append(
            f'<div><a href="genre/{html.escape(genre)}.html">{html.escape(genre)}</a> '
            f'<span class="count">{len(works):,} texts</span><br>'
            f'<span class="count">{description}</span></div>'
        )
    parts.append("</div>")
    total = sum(len(w) for w in genres.values())
    parts.insert(
        0,
        f'<p class="sub">{total:,} texts. Click any word for its lemma and '
        "morphology.</p>",
    )
    return _page("తెలుగు గ్రంథాలయం", "\n".join(parts), depth=0)


def render_genre(genre: str, entries: list[tuple[str, str]]) -> str:
    """One genre's table of contents. `entries` are (title, slug) pairs."""
    parts = [f"<h1>{html.escape(genre)}</h1>"]
    parts.append(f'<p class="sub">{len(entries):,} texts</p>')
    parts.append('<ul class="works">')
    for title, slug in sorted(entries):
        parts.append(
            f'<li><a href="../text/{slug}.html">{html.escape(title)}</a></li>'
        )
    parts.append("</ul>")
    return _page(genre, "\n".join(parts), depth=1)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
