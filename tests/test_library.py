"""Tests for the Telugu library.

Run with: python3 tests/test_library.py

Plain asserts in a script, like telugu-morph's suite, so this runs on a stock Python
with no installation step. Network tests are skipped when telugu-morph or a cached
corpus is absent, so the file is always runnable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "telugu-morph" / "src")
)

from telugu_library import site
from telugu_library.catalogue import Work, walk_genre
from telugu_library.reader import Token, parse
from telugu_library.wikisource import Page, VERSE_NUMBER

failures = 0
checks = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global failures, checks
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL  {label}")
        if detail:
            print(f"      {detail}")


def eq(actual, expected, label: str) -> None:
    check(actual == expected, label, f"got {actual!r}, expected {expected!r}")


# --- Provenance -----------------------------------------------------------

page = Page(title="12. కుంతీదేవి శ్రీకృష్ణుని స్తుతించుట", text="కం. ఇది ఒక పద్యం (1-185)", revision=20897)
check("te.wikisource.org" in page.url, "a page knows its source URL")
check("CC BY-SA" in page.attribution, "attribution names the licence")
eq(page.verse_numbers(), ["1-185"], "the canonical verse number survives fetching")

# A verse number is navigation, not vocabulary — it must be recognised as such.
eq(bool(VERSE_NUMBER.search("(1-185)")), True, "verse numbers are recognised")
eq(bool(VERSE_NUMBER.search("ఇల్లు")), False, "a Telugu word is not a verse number")


# --- Slugs ----------------------------------------------------------------

work = Work(title="12. కుంతీదేవి శ్రీకృష్ణుని స్తుతించుట", genre="పురాణాలు")
eq(len(work.slug), 12, "a slug is a short hash")
check(work.slug.isalnum(), "a slug is URL-safe")
# Stable across runs, or every link in the site breaks on rebuild.
eq(work.slug, Work(title=work.title, genre="x").slug, "slugs are stable")


# --- A fake analyser, so parsing is testable without the corpus -----------

class _Reading:
    def __init__(self, lemma, tag, pos, steps=1):
        self.lemma, self.tag, self.pos = lemma, tag, pos
        self.path = type("P", (), {"steps": (1,) * steps})()


class _Analyser:
    """Answers for a handful of words and gives up on the rest, like the real one."""

    lexicon = {"ఇల్లు": 1572, "ప్రకృతి": 3061}

    def analyse(self, word, max_results=8):
        if word == "ఇంటికి":
            return [_Reading("ఇల్లు", "noun<dat>", "noun")]
        if word == "ప్రకృతికిఁ":
            return [_Reading("ప్రకృతి", "noun<dat>", "noun")]
        if word == "డాఢ్యుఁడు":
            # A sandhi-split fragment: it parses, but the lemma is not a word.
            return [_Reading("డాఢ్యుడు", "noun", "noun")]
        return [_Reading(word, "noun", "noun", steps=0)]


analyser = _Analyser()
text = "కం. ఇంటికి ప్రకృతికిఁ డాఢ్యుఁడు (1-185)\n\nవ. ఇంటికి."
document = parse("T", text, analyser, lexicon=_Analyser.lexicon)

eq(len(document.lines), 3, "blank lines are kept, so stanzas can be separated")
eq(document.lines[0].marker, "కం.", "a verse marker is recognised")
eq(document.lines[2].marker, "వ.", "a prose marker is recognised")
eq(document.lines[0].verse, "1-185", "the line carries its verse number")

# The fragment must be reported as a gap, not glossed with a non-word. Without this
# the site claimed 19.1% coverage where the honest figure was 16.5%.
tokens = {t.surface: t for line in document.lines for t in line.tokens}
eq(tokens["ఇంటికి"].lemma, "ఇల్లు", "an attested lemma is glossed")
eq(tokens["ఇంటికి"].unanalysed, False, "a real gloss is not marked as a gap")
eq(tokens["డాఢ్యుఁడు"].unanalysed, True,
   "a fragment whose lemma is unattested is reported as a gap")

# Punctuation and verse numbers must never reach the analyser.
eq(Token(surface=" ").is_telugu, False, "a space is not a Telugu token")
eq(Token(surface="(1-185)").is_telugu, False, "a verse number is not a Telugu token")
eq(Token(surface="ఇల్లు").is_telugu, True, "a Telugu word is a Telugu token")

# Coverage counts only Telugu tokens, and only honest glosses.
check(0 < document.coverage < 100, "coverage is a real fraction",
      f"got {document.coverage}")


# --- Rendering ------------------------------------------------------------

document.url = "https://te.wikisource.org/wiki/T"
document.path = ["పురాణాలు", "భాగవతము"]
rendered = site.render_document(document)

check(rendered.startswith("<!DOCTYPE html>"), "a rendered page is a document")
check('lang="te"' in rendered, "the page declares Telugu")
check('data-lemma="ఇల్లు"' in rendered, "an analysed token carries its lemma")
check('class="gap"' in rendered, "an unanalysed token is rendered inert")
# The fragment must not be clickable — that is the whole point of marking it.
check('data-lemma="డాఢ్యుడు"' not in rendered,
      "a fragment is not offered as a clickable gloss")
check("CC BY-SA" in rendered, "every page carries the licence")
check("te.wikisource.org" in rendered, "every page links to its source")

# HTML escaping: a text containing markup must not be able to inject it.
nasty = parse("T", "కం. <script>alert(1)</script> ఇంటికి", analyser,
              lexicon=_Analyser.lexicon)
check("<script>alert" not in site.render_document(nasty),
      "raw markup in a source text is escaped")

index = site.render_index({"పురాణాలు": [("a", "b")]}, {"పురాణాలు": "Purāṇas"})
check("పురాణాలు" in index, "the index lists genres")
genre_page = site.render_genre("పురాణాలు", [("శ్రీమదాంధ్ర భాగవతము", "abc123")])
check("../text/abc123.html" in genre_page, "a genre page links to its texts")


# --- Report ---------------------------------------------------------------

print()
if failures:
    print(f"{failures} of {checks} checks FAILED")
    sys.exit(1)
print(f"all {checks} checks passed")
