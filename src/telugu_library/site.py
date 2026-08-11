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
#panel .dict { font-size: .8rem; }
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
      + '<span class="tag">' + w.dataset.tag + '</span>'
      + ' &nbsp; <a class="dict" target="_blank" rel="noopener" href="'
      + 'https://andhrabharati.com/dictionary/?w=' + encodeURIComponent(w.dataset.lemma)
      + '">dictionary &rarr;</a>';
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


def _page(
    title: str,
    body: str,
    depth: int = 0,
    panel: str | None = None,
    payload: str = "",
) -> str:
    """One HTML page. `depth` sets how far back the root is, for relative links.

    `payload` is the URL of a JSON analysis file for pages that fetch it rather than
    inlining it into the markup.
    """
    up = "../" * depth
    attribute = f' data-payload="{html.escape(payload)}"' if payload else ""
    return f"""<!DOCTYPE html>
<html lang="te">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}{VERSE_CSS}</style>
<body{attribute}>
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
<script>{panel or PANEL_JS}</script>
</body></html>
"""


def render_document(document: Document, depth: int = 1) -> str:
    """A text as a reading page, every analysed token clickable."""
    parts: list[str] = []
    breadcrumb = " › ".join(html.escape(p) for p in document.path)
    parts.append(f'<h2>{breadcrumb}</h2>')
    parts.append(f"<h1>{html.escape(document.title)}</h1>")
    if document.language == "sanskrit":
        # Said plainly rather than left as a silent 0%. A reader who finds an unglossed
        # page deserves to know it is unglossed *because the text is Sanskrit*, not
        # because the analyser is broken.
        parts.append(
            f'<p class="sub">{document.token_count:,} words · '
            "Sanskrit in Telugu script, so not glossed — this project analyses "
            "Telugu · "
            f'<a href="{html.escape(document.url)}">source</a></p>'
        )
    else:
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
    # Insertion order, not size order. For a work in books the sequence *is* the
    # structure, and sorting the Bhāgavatam's skandhams by section count would present
    # the tenth book first.
    for genre, works in genres.items():
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


def render_verse_text(document) -> str:
    """A Bhāgavatam-style annotated text: verse as printed, morphemes on click.

    Different from `render_document` because the material is different. Here every token
    has an editorial morpheme breakdown, so the panel shows the *structure* of a word —
    `రక్షైకారంభకు` = `రక్ష` + `ఏక` + `ఆరంభ` + `కున్` — rather than a single lemma. That
    breakdown is the thing a reader of classical verse actually needs, and it is what no
    amount of automatic sandhi reversal produced reliably.

    `document` is a `bhagavatam.AnnotatedText`.
    """
    parts: list[str] = [f"<h1>{html.escape(document.title)}</h1>"]
    annotated = document.annotated_verses
    total = len(document.verses)
    summary = f"{total:,} verses"
    if annotated < total:
        summary += f", {annotated:,} with a word-by-word gloss"
    summary += f" · {document.morpheme_count:,} glossed morphemes"
    parts.append(
        f'<p class="sub">{summary} · '
        f'<a href="{html.escape(document.url)}">source</a></p>'
    )

    for verse in document.verses:
        parts.append('<div class="verse">')
        parts.append(
            f'<div class="vref">{verse.reference}'
            f' <span class="metre">{html.escape(verse.metre_name)}</span></div>'
        )
        rendered: list[str] = []
        for token, morphemes in verse.alignment:
            escaped = html.escape(token)
            if not morphemes:
                rendered.append(f'<span class="gap">{escaped}</span>')
                continue
            payload = json.dumps(
                [
                    {
                        "f": m.form,
                        "g": m.gloss,
                        "p": m.pos or "",
                        "e": m.etymology or "",
                        "n": m.english or "",
                        "s": 1 if m.shared else 0,
                    }
                    for m in morphemes
                ],
                ensure_ascii=False,
            )
            rendered.append(
                f'<span class="w" data-m="{html.escape(payload)}">{escaped}</span>'
            )
        parts.append('<p class="line">' + " ".join(rendered) + "</p>")
        if verse.paraphrase:
            # The editor's prose paraphrase, quoted rather than rewritten. It is their
            # scholarship and it is what makes a 15th-century verse comprehensible.
            parts.append(
                f'<p class="bhavamu">{html.escape(verse.paraphrase)}</p>'
            )
        parts.append("</div>")

    return _page(document.title, "\n".join(parts), depth=1, panel=VERSE_PANEL_JS)


# The morpheme panel. Shows each piece of the clicked word with the editor's gloss, the
# part of speech where a dictionary gave one, and a link to andhrabharati — which is how
# this project uses that site: as a place to send the reader, not a corpus to copy.
VERSE_PANEL_JS = """
(function () {
  var panel = document.getElementById('panel');
  if (!panel) return;
  document.addEventListener('click', function (e) {
    var w = e.target.closest ? e.target.closest('.w') : null;
    if (!w) return;
    var ms = JSON.parse(w.dataset.m);
    var rows = ms.map(function (m) {
      var bits = ['<span class="lemma">' + m.f + '</span>'];
      // A word that runs across the line break is listed under both halves. Saying so
      // stops it looking like the wrong word was attached.
      if (m.s) bits.push('<span class="shared">spans the line break</span>');
      if (m.g) bits.push('<span class="tel">' + m.g + '</span>');
      if (m.p) bits.push('<span class="tag">' + m.p + '</span>');
      if (m.e) bits.push('<span class="tag">' + m.e + '</span>');
      if (m.n) bits.push('<span class="en">' + m.n + '</span>');
      bits.push('<a class="dict" target="_blank" rel="noopener" href="'
        + 'https://andhrabharati.com/dictionary/?w=' + encodeURIComponent(m.f)
        + '">\\u2197</a>');
      return '<div class="mrow">' + bits.join(' &nbsp; ') + '</div>';
    }).join('');
    panel.innerHTML = '<span class="close">close</span>'
      + '<div class="surface">' + w.textContent + '</div>' + rows;
    panel.classList.add('on');
  });
  panel.addEventListener('click', function (e) {
    if (e.target.classList.contains('close')) panel.classList.remove('on');
  });
})();
"""

VERSE_CSS = """
.verse { margin: 0 0 1.6rem; }
.vref { color: var(--dim); font-size: .75rem; letter-spacing: .04em; }
.metre { font-style: italic; }
.mrow { padding: .2rem 0; }
.naama { font-size: 1.25rem; }
.alt-gloss { border-left-style: dotted; }
.bhavamu {
  margin: .35rem 0 0 1.5rem; color: var(--dim); font-size: .92rem;
  border-left: 2px solid var(--rule); padding-left: .8rem;
}
#panel .tel { color: var(--ink); }
#panel .en { color: var(--dim); font-style: italic; }
#panel .shared { color: var(--dim); font-size: .75rem; }
"""


def render_sahasranamam(document) -> str:
    """The thousand names, each with its explanation.

    A list rather than a verse page, because the source is a list — one name per entry with
    a Telugu explanation. There is no metrical line to preserve and no alignment to do, so
    the reader gets the name, its number for citation, and the meaning.

    A multi-word name has its words shown separately, since that is the one place a reader
    needs help and as far as the source goes: `భూతభవ్యభవత్ ప్రభుః` is two words, and
    knowing where the break falls is most of what a learner wants.
    """
    parts: list[str] = [f"<h1>{html.escape(document.title)}</h1>"]
    complete = "all 1,000" if document.complete else f"{len(document.names):,} of 1,000"
    parts.append(
        f'<p class="sub">{complete} names, each with a Telugu explanation · '
        f'<a href="{html.escape(document.url)}">source</a></p>'
    )

    for entry in document.names:
        words = "".join(
            f'<span class="w" data-m="{html.escape(json.dumps([{"f": word, "g": "", "p": "", "e": "", "n": "", "s": 0}], ensure_ascii=False))}">{html.escape(word)}</span>'
            for word in entry.words
        )
        parts.append('<div class="verse">')
        parts.append(f'<div class="vref">{entry.number}</div>')
        parts.append(f'<p class="line naama">{words}</p>')
        parts.append(f'<p class="bhavamu">{html.escape(entry.meaning)}</p>')
        for alternative in entry.alternatives:
            parts.append(
                f'<p class="bhavamu alt-gloss">{html.escape(alternative)}</p>'
            )
        parts.append("</div>")

    return _page(document.title, "\n".join(parts), depth=1, panel=VERSE_PANEL_JS)


def render_library(works: list[tuple[str, str]], entries: dict) -> str:
    """The front page: the works in the library, each with a way in.

    Distinct from `render_index`, which lists the parts of one work. A library index that
    presented the Bhāgavatam's twelve skandhams beside a second text as if they were peers
    would misrepresent the structure.
    """
    parts = ['<p class="sub">Click any word for its meaning.</p>']
    parts.append('<div class="genre-grid">')
    for title, description in works:
        links = entries.get(title, [])
        target = links[0][1].replace("../", "") + ".html" if links else "#"
        label = links[0][0] if links else ""
        parts.append(
            f'<div><a href="{html.escape(target)}">{html.escape(title)}</a> '
            f'<span class="count">{html.escape(label)}</span><br>'
            f'<span class="count">{html.escape(description)}</span></div>'
        )
    parts.append("</div>")
    return _page("తెలుగు గ్రంథాలయం", "\n".join(parts), depth=0)


def render_satakam(
    verses,
    title: str,
    slug: str,
    provenance: str = "",
) -> tuple[str, str]:
    """A śatakam with its word-by-word analysis, as (html, payload_json).

    Serves Vemana and Sumatī both, because the two are the same shape: 100-odd short
    verses, a flat morpheme list per verse, and the shared aligner mapping morphemes onto
    printed tokens. Writing a second renderer would have meant a second copy of the
    payload bug fixed below.

    The provenance line is deliberately explicit. For the Bhāgavatam the gloss is a
    scholar's, quoted; here it is this project's own analysis, and a reader deserves to
    know which they are looking at before they rely on it.

    The analysis is fetched rather than inlined. Writing it into each word's `data-m`
    made a page of 146 short verses **7.3 MB**: there are only 143 distinct payloads, one
    per verse, but they were copied into 2,015 word attributes, so 98% of the file was
    duplication. Each word now carries its verse number and its own token index, and the
    panel looks up just that token's morphemes.
    """
    parts: list[str] = [f"<h1>{html.escape(title)}</h1>"]
    morphemes = sum(len(v.morphemes) for v in verses)
    summary = f"{len(verses):,} verses · {morphemes:,} morphemes"
    if provenance:
        summary += f" · {provenance}"
    parts.append(f'<p class="sub">{summary}</p>')

    payload: dict[str, dict] = {}
    for verse in verses:
        parts.append('<div class="verse">')
        parts.append(f'<div class="vref">{verse.reference}</div>')
        key = str(verse.number)
        # Per token, not per verse. Before this, every word in a verse carried the whole
        # verse's gloss, so clicking `రాయి` listed all twelve morphemes of all four lines.
        tokens: dict[str, list] = {}
        for position, (_, _, token_morphemes) in enumerate(verse.alignment):
            tokens[str(position)] = [
                {
                    "f": morpheme.form,
                    "g": morpheme.gloss,
                    "s": 1 if morpheme.shared else 0,
                }
                for morpheme in token_morphemes
            ]
        payload[key] = {"tokens": tokens}

        # Rendered line by line, keeping the poet's lineation, with each token's index so
        # the panel can find it.
        position = 0
        for line_index, line in enumerate(verse.lines):
            rendered: list[str] = []
            for token in line.split():
                escaped = html.escape(token)
                if position < len(verse.alignment) and verse.alignment[position][1] == token:
                    rendered.append(
                        f'<span class="w" data-v="{key}" data-p="{position}">'
                        f"{escaped}</span>"
                    )
                    position += 1
                else:
                    # A token the aligner skipped — punctuation or a digit. Inert, and it
                    # looks inert, rather than offering a panel with nothing in it.
                    rendered.append(f'<span class="gap">{escaped}</span>')
            parts.append('<p class="line verse-line">' + " ".join(rendered) + "</p>")
        parts.append("</div>")

    document = _page(
        title, "\n".join(parts), depth=1, panel=SATAKAM_PANEL_JS,
        payload=f"../data/{slug}.json",
    )
    return document, json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# The śatakam panel. One fetch for the whole text, then every click is a dictionary lookup
# of that token's own morphemes.
SATAKAM_PANEL_JS = """
(function () {
  var panel = document.getElementById('panel');
  if (!panel) return;
  var url = document.body.dataset.payload;
  var data = null, pending = null;

  function load() {
    if (data) return Promise.resolve(data);
    if (!pending) {
      pending = fetch(url).then(function (r) { return r.json(); })
        .then(function (j) { data = j; return j; });
    }
    return pending;
  }

  function row(m) {
    var bits = ['<span class="lemma">' + m.f + '</span>'];
    // A word running across the line break is listed under both halves; saying so stops
    // it looking like the wrong word was attached.
    if (m.s) bits.push('<span class="shared">spans the line break</span>');
    bits.push('<span class="tel">' + m.g + '</span>');
    bits.push('<a class="dict" target="_blank" rel="noopener" href="'
      + 'https://andhrabharati.com/dictionary/?w=' + encodeURIComponent(m.f)
      + '">\\u2197</a>');
    return '<div class="mrow">' + bits.join(' &nbsp; ') + '</div>';
  }

  document.addEventListener('click', function (e) {
    var w = e.target.closest ? e.target.closest('.w') : null;
    if (!w) return;
    var key = w.dataset.v, pos = w.dataset.p;
    panel.innerHTML = '<span class="close">close</span><div class="surface">'
      + w.textContent + '</div><div class="mrow dim">…</div>';
    panel.classList.add('on');
    load().then(function (j) {
      var verse = j[key];
      if (!verse) return;
      var ms = verse.tokens[pos] || [];
      panel.innerHTML = '<span class="close">close</span>'
        + '<div class="surface">' + w.textContent + '</div>'
        + (ms.length ? ms.map(row).join('')
                     : '<div class="mrow dim">no analysis</div>');
    }).catch(function () {
      panel.innerHTML = '<span class="close">close</span>'
        + '<div class="surface">' + w.textContent + '</div>'
        + '<div class="mrow dim">analysis unavailable</div>';
    });
  });
  panel.addEventListener('click', function (e) {
    if (e.target.classList.contains('close')) panel.classList.remove('on');
  });
})();
"""


TITLE_VEMANA = "వేమన శతకము"


def render_vemana(verses, url: str = "") -> tuple[str, str]:
    """Vemana, kept as a named entry point so callers need not know the shared shape."""
    return render_satakam(
        verses, TITLE_VEMANA, "vemana-satakam",
        "the word-by-word analysis here is this project's own, not a scholar's — "
        "no published gloss of Vemana exists online",
    )
