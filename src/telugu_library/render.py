"""Rendering from the store, with the analysis fetched rather than inlined.

The old renderer put every morpheme's form, gloss, part of speech and etymology into a
`data-m` attribute on every clickable word. That made each page average **141 KB** and
the site 94.5 MB, and it meant the analysis existed nowhere but the markup.

Here the page carries only the text and a token index; the analysis for a section lives
beside it as one JSON file, fetched on the reader's first click and cached by the browser
thereafter. Two consequences worth having:

  * the page is small, so it renders before the analysis has downloaded at all — a
    reader who only wants to *read* never pays for the annotation;
  * the analysis is a real artifact with a URL, which makes it an API by construction.
    `/data/<slug>.json` is exactly what a client would want, so there is nothing extra
    to build to serve one.

Still static: these are plain files written once at build time. Nothing here needs a
server, and `file://` works because the payload is fetched relative to the page.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import store
from .site import CSS, VERSE_CSS, write
from .wikisource import LICENCE, LICENCE_URL

# Fetches the section's analysis once, on the first click, then reads it from memory.
# Deliberately vanilla: no framework, no build step, and it degrades to plain text if
# the fetch fails rather than leaving dead underlines.
PANEL_JS = """
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
    if (m.g) bits.push('<span class="tel">' + m.g + '</span>');
    if (m.p) bits.push('<span class="tag">' + m.p + '</span>');
    if (m.e) bits.push('<span class="tag">' + m.e + '</span>');
    // Provenance, shown only when it is not the editorial gloss — so a reader can tell
    // "a scholar wrote this" from "we inferred this".
    if (m.c !== undefined && m.c < 1) {
      bits.push('<span class="prov">inferred' +
        (m.a ? ' — ' + m.a : '') + '</span>');
    }
    bits.push('<a class="dict" target="_blank" rel="noopener" href="'
      + 'https://andhrabharati.com/dictionary/?w=' + encodeURIComponent(m.f)
      + '">\\u2197</a>');
    return '<div class="mrow">' + bits.join(' &nbsp; ') + '</div>';
  }

  document.addEventListener('click', function (e) {
    var w = e.target.closest ? e.target.closest('.w') : null;
    if (!w) return;
    var vid = w.dataset.v, pos = w.dataset.p;
    panel.innerHTML = '<span class="close">close</span><div class="surface">'
      + w.textContent + '</div><div class="mrow dim">…</div>';
    panel.classList.add('on');
    load().then(function (j) {
      var verse = j.verses[vid];
      if (!verse) return;
      var ms = (verse.tokens[pos] || {}).m || [];
      panel.innerHTML = '<span class="close">close</span>'
        + '<div class="surface">' + w.textContent + '</div>'
        + (ms.length ? ms.map(row).join('') : '<div class="mrow dim">no analysis</div>');
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

EXTRA_CSS = """
#panel .prov { color: var(--dim); font-size: .75rem; font-style: italic; }
#panel .dim { color: var(--dim); }
"""


def _page(title: str, body: str, payload_url: str, depth: int = 1) -> str:
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="te">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}{VERSE_CSS}{EXTRA_CSS}</style>
<body data-payload="{html.escape(payload_url)}">
<div class="wrap">
<header><h1><a href="{up}index.html">తెలుగు గ్రంథాలయం</a></h1>
<p class="sub">A parsing reader for Telugu literature</p></header>
{body}
<footer>
Texts from <a href="https://te.wikisource.org">Telugu Wikisource</a>,
<a href="{LICENCE_URL}">{LICENCE}</a>.
</footer>
</div>
<div id="panel"></div>
<script>{PANEL_JS}</script>
</body></html>
"""


def section_payload(connection, section_id: int) -> dict:
    """The analysis for a whole section, as one fetchable object.

    Per-section rather than per-verse because a reader moves between verses on one page,
    and one request for the page's worth of analysis beats one per word. Keys are verse
    node ids, matching the `data-v` attributes in the markup — ids, never offsets, so a
    later correction cannot silently shift the mapping.
    """
    verses: dict[str, dict] = {}
    rows = connection.execute(
        """
        SELECT n.id AS node_id, t.id AS token_id, t.position,
               m.ordinal, m.form, m.pos, m.etymology, tm.shared,
               g.text AS gloss, g.confidence, g.annotator
          FROM node n
          JOIN token t ON t.node_id = n.id
          LEFT JOIN token_morpheme tm ON tm.token_id = t.id
          LEFT JOIN morpheme m ON m.id = tm.morpheme_id
          LEFT JOIN gloss g ON g.morpheme_id = m.id AND g.superseded_by IS NULL
         WHERE n.parent_id = ? AND n.kind = 'verse'
         ORDER BY n.path, t.position, m.ordinal
        """,
        (section_id,),
    ).fetchall()
    for row in rows:
        verse = verses.setdefault(str(row["node_id"]), {"tokens": {}})
        token = verse["tokens"].setdefault(str(row["position"]), {"m": []})
        if row["form"] is None:
            continue
        entry = {
            "f": row["form"],
            "g": row["gloss"] or "",
            "p": row["pos"] or "",
            "e": row["etymology"] or "",
            "s": row["shared"] or 0,
        }
        # Confidence and annotator travel with the gloss, so the UI can distinguish a
        # scholar's reading from a computed one. Omitted when editorial, to keep the
        # payload small — absence means confidence 1.
        if row["confidence"] is not None and row["confidence"] < 1:
            entry["c"] = row["confidence"]
            if row["annotator"]:
                entry["a"] = row["annotator"]
        token["m"].append(entry)
    return {"verses": verses}


def render_section(connection, section_id: int, slug: str) -> tuple[str, str]:
    """One section as (html, payload_json)."""
    section = connection.execute(
        "SELECT label, meta FROM node WHERE id = ?", (section_id,)
    ).fetchone()
    meta = json.loads(section["meta"] or "{}")
    verses = connection.execute(
        "SELECT id, urn, ref FROM node WHERE parent_id = ? AND kind = 'verse'"
        " ORDER BY path",
        (section_id,),
    ).fetchall()

    counts = connection.execute(
        """
        SELECT COUNT(DISTINCT m.id) AS morphemes,
               COUNT(DISTINCT CASE WHEN m.id IS NOT NULL THEN n.id END) AS annotated
          FROM node n LEFT JOIN morpheme m ON m.node_id = n.id
         WHERE n.parent_id = ? AND n.kind = 'verse'
        """,
        (section_id,),
    ).fetchone()

    parts = [f"<h1>{html.escape(section['label'])}</h1>"]
    summary = f"{len(verses):,} verses"
    if counts["annotated"] < len(verses):
        summary += f", {counts['annotated']:,} with a word-by-word gloss"
    summary += f" · {counts['morphemes']:,} glossed morphemes"
    if meta.get("url"):
        summary += f' · <a href="{html.escape(meta["url"])}">source</a>'
    parts.append(f'<p class="sub">{summary}</p>')

    for verse in verses:
        tokens = connection.execute(
            "SELECT position, text,"
            " (SELECT COUNT(*) FROM token_morpheme tm WHERE tm.token_id = token.id)"
            "   AS n"
            " FROM token WHERE node_id = ? ORDER BY position",
            (verse["id"],),
        ).fetchall()
        metre = connection.execute(
            "SELECT name FROM metrical_annotation WHERE node_id = ? LIMIT 1",
            (verse["id"],),
        ).fetchone()
        paraphrase = connection.execute(
            "SELECT text FROM paraphrase WHERE node_id = ? LIMIT 1", (verse["id"],)
        ).fetchone()

        parts.append('<div class="verse">')
        parts.append(
            f'<div class="vref">{html.escape(verse["ref"])}'
            f' <span class="metre">{html.escape(metre["name"] if metre else "")}</span>'
            "</div>"
        )
        rendered = []
        for token in tokens:
            escaped = html.escape(token["text"])
            if not token["n"]:
                rendered.append(f'<span class="gap">{escaped}</span>')
            else:
                # Two small integers instead of a serialised morpheme list. This is the
                # whole of the size win.
                rendered.append(
                    f'<span class="w" data-v="{verse["id"]}"'
                    f' data-p="{token["position"]}">{escaped}</span>'
                )
        parts.append('<p class="line">' + " ".join(rendered) + "</p>")
        if paraphrase:
            parts.append(
                f'<p class="bhavamu">{html.escape(paraphrase["text"])}</p>'
            )
        parts.append("</div>")

    payload = json.dumps(
        section_payload(connection, section_id), ensure_ascii=False,
        separators=(",", ":"),
    )
    return _page(section["label"], "\n".join(parts), f"../data/{slug}.json"), payload


def render_all(connection, out: Path) -> dict:
    """Every section in the store, as a page plus a payload."""
    sections = connection.execute(
        "SELECT id, label, parent_id FROM node WHERE kind = 'section' ORDER BY path"
    ).fetchall()
    html_bytes = payload_bytes = 0
    written = 0
    for section in sections:
        slug = f"s{section['id']:05d}"
        page, payload = render_section(connection, section["id"], slug)
        write(out / "text" / f"{slug}.html", page)
        write(out / "data" / f"{slug}.json", payload)
        html_bytes += len(page.encode())
        payload_bytes += len(payload.encode())
        written += 1
    return {
        "sections": written,
        "html_mb": html_bytes / 1048576,
        "payload_mb": payload_bytes / 1048576,
        "mean_page_kb": html_bytes / written / 1024 if written else 0,
    }
