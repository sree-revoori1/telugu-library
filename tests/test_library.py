"""Tests for the Telugu library.

Run with: python3 tests/test_library.py

Plain asserts in a script, like telugu-morph's suite, so this runs on a stock Python
with no installation step. Network tests are skipped when telugu-morph or a cached
corpus is absent, so the file is always runnable.
"""

from __future__ import annotations

import json
import re
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


# --- Telugu vs Sanskrit ---------------------------------------------------

from telugu_library.language import is_sanskrit, sanskrit_share

# The finding that mattered most: Wikisource's epic category is dominated by the
# Vālmīki Rāmāyaṇam, which is Sanskrit in Telugu script. A Telugu analyser produces
# confident nonsense on it, so it must be detected and left unglossed.
sanskrit = "తతః సర్గః తస్మాత్ దేశాత్ ప్రతస్థిరే రామస్య వృక్షౌ " * 20
telugu = "ఆ ఇల్లు చాలా పెద్దది అని అతను చెప్పాడు కూడా వారు వచ్చి ఉన్నారు " * 20
check(is_sanskrit(sanskrit), "Sanskrit in Telugu script is detected",
      f"share={sanskrit_share(sanskrit):.2f}")
check(not is_sanskrit(telugu), "Telugu is not flagged as Sanskrit",
      f"share={sanskrit_share(telugu):.2f}")
# Too short to judge — a title can hit any ratio by accident.
check(not is_sanskrit("సర్గః"), "a short string is not judged")

document = parse("S", sanskrit, analyser, lexicon=_Analyser.lexicon)
eq(document.language, "sanskrit", "a Sanskrit document is labelled")
eq(document.analysed_count, 0, "Sanskrit is not glossed at all")


# --- Coverage counting ----------------------------------------------------

# Regression: an uninflected word analyses to itself with no steps, and that is the
# correct answer — most Telugu tokens in running text are uninflected. Requiring a
# suffix to have been peeled marked `ఈ` (294,297 occurrences) and `మీ` (148,590) as
# failures and understated coverage by fifty points.
class _Uninflected:
    lexicon = {"ఈ": 294297}

    def analyse(self, word, max_results=8):
        return [_Reading("ఈ", "determiner", "determiner", steps=0)]


plain = parse("U", "ఈ", _Uninflected(), lexicon=_Uninflected.lexicon)
token = plain.lines[0].tokens[0]
eq(token.unanalysed, False,
   "regression: an attested uninflected word counts as glossed")
eq(plain.coverage, 100.0, "coverage counts it")

# Telugu digits are not words. `[ఀ-౿]` wrongly includes U+0C66-6F, so every verse
# number written in Telugu numerals was sent to the analyser.
eq(Token(surface="౧౨౩").is_telugu, False, "Telugu digits are not word tokens")
eq(Token(surface="౬౪").is_telugu, False, "a two-digit Telugu numeral is not a word")


# --- The Bhāgavatam pipeline -----------------------------------------------

from telugu_library.bhagavatam import (
    Morpheme, SUFFIXES, align, aksharams, parse_page, split_gloss,
)

# The discovery the project turned on: Wikisource's Bhāgavatam carries an editorial
# word-by-word gloss, so the sandhi splitting that no automatic analyser managed is
# already done by a scholar.
SAMPLE = (
    "తెభా-1-1-శా.శ్రీ కైవల్య పదంబుఁ జేరుటకునై చింతించెదన్"
    "టీక:- శ్రీ = శుభకర మైన; కైవల్య = ముక్తి; పదంబున్ = స్థితిని; "
    "చేరుట = పొందుట; కున్ = కోసము; ఐ = ఐ; చింతించెదన్ = ప్రార్థించెదన్"
    "భావము:- మోక్షము చేరుటకై ప్రార్థించెదను."
)
verses = parse_page(SAMPLE)
eq(len(verses), 1, "a verse is parsed from its id marker")
verse = verses[0]
eq(verse.reference, "1-1", "the citable reference is recovered")
eq(verse.metre_name, "śārdūlam", "the metre abbreviation is expanded")
eq(len(verse.morphemes), 7, "every gloss pair becomes a morpheme")
eq(verse.morphemes[0].gloss, "శుభకర మైన", "the editor's meaning is kept verbatim")

# Regression: the paraphrase is a separate field. Without splitting it off, it was
# swallowed into the last morpheme's meaning, so `చింతించెదన్` carried a whole sentence.
check(verse.paraphrase.startswith("మోక్షము"), "the భావము paraphrase is separated",
      f"got {verse.paraphrase[:40]!r}")
check("భావము" not in verse.morphemes[-1].gloss,
      "regression: the paraphrase does not leak into the last gloss")

# Alignment counts aksharams, not codepoints. `జేరుటకునై` is 5 aksharams and 9
# codepoints; its three morphemes are 6 aksharams and 10 codepoints — so codepoint
# arithmetic bears no relation to the fit, and drifted a token out of step in one line.
eq(len(aksharams("జేరుటకునై")), 5, "aksharams are counted, not codepoints")
alignment = align(verse)
placed = {token: [m.form for m in ms] for token, ms in alignment}
eq(placed.get("జేరుటకునై"), ["చేరుట", "కున్", "ఐ"],
   "a sandhi-fused token aligns to its three morphemes")
eq(placed.get("పదంబుఁ"), ["పదంబున్"], "a token with sandhi at its edge still aligns")
# No gloss may be dropped: every morpheme is placed somewhere.
eq(sum(len(ms) for _, ms in alignment), len(verse.morphemes),
   "alignment places every morpheme")

# Verses with no editorial gloss are skipped rather than shown unexplained.
eq(len(parse_page("తెభా-1-2-వ.ఇది గ్లాసు లేని పద్యము.")), 0,
   "a verse without a టీక gloss is skipped")
eq(len(parse_page("తెభా-1-2-వ.ఇది గ్లాసు లేని పద్యము.", glossed_only=False)), 1,
   "...unless the caller asks for it")

# Bound morphemes are settled by the closed inflectional inventory, not the dictionary.
# `కున్` is the dative suffix and matches only Urdu dictionaries, which report a noun.
check(Morpheme(form="కున్", gloss="కోసము").is_suffix, "a case suffix is recognised")
check(Morpheme(form="కున్", gloss="కోసము").accounted,
      "a suffix counts as accounted for without a dictionary")
check(not Morpheme(form="కైవల్య", gloss="ముక్తి").is_suffix,
      "a lexical word is not a suffix")

eq(split_gloss("అ = ఒకటి; ఇ = రెండు"), [("అ", "ఒకటి"), ("ఇ", "రెండు")],
   "gloss pairs split on semicolons")


# --- The annotation store -------------------------------------------------
# The store exists so the analysis is queryable rather than embedded in markup. What
# needs testing is not that SQLite works, but that the four decisions which are expensive
# to reverse actually hold: the path hierarchy, id-based joins, the many-to-many link, and
# versioned provenance.

from telugu_library import store as store_module

_conn = store_module.connect(":memory:", fresh=False)
_writer = store_module.Writer(_conn)
_src = _writer.add_source("test", title="a test", kind="editorial")
_corpus = _writer.add_node("corpus", label="c", urn="c")
_work = _writer.add_node("work", label="w", parent_id=_corpus, urn="w")
_book = _writer.add_node("book", label="b", parent_id=_work, urn="w:1")


class _M:
    """A stand-in for bhagavatam.Morpheme, so the store is tested without a network."""

    def __init__(self, form, gloss, shared=False, pos=None):
        self.form, self.gloss, self.shared, self.pos = form, gloss, shared, pos
        self.etymology = None
        self.is_suffix = False


# A morpheme straddling two tokens, which is the case a tree cannot represent:
# `ఆరూఢుండు` has characters in both printed tokens.
_m1 = _M("పరికర", "సన్నాహము")
_m2 = _M("ఆరూఢుండు", "ఎక్కినవాడు", shared=True)
_m3 = _M("అగున్", "అవును")
_verse = _writer.add_verse(
    _book,
    urn="w:1.1",
    ref="1-1",
    alignment=[("పరికరారూఢుం", [_m1, _m2]), ("డగు", [_m2, _m3])],
    morphemes=[_m1, _m2, _m3],
    paraphrase="ఒక భావము",
    metre_code="సీ",
    metre_name="సీస పద్యము",
    source_id=_src,
)
_conn.commit()

# The materialized path makes a subtree one indexed prefix match. Depth is derived, not
# stored twice.
eq(len(store_module.subtree(_conn, _work, "verse")), 1,
   "a subtree query finds the verse under the work")
eq(len(store_module.subtree(_conn, _book, "verse")), 1,
   "...and under the book")
_paths = [r["path"] for r in _conn.execute(
    "SELECT path FROM node ORDER BY path").fetchall()]
check(all(_paths[i] < _paths[i + 1] for i in range(len(_paths) - 1)),
      "paths sort in tree order, which is what makes ORDER BY path correct")
eq(_conn.execute("SELECT depth FROM node WHERE id=?", (_verse,)).fetchone()[0], 4,
   "depth follows from the path")

# The many-to-many link, and the flag that says why it exists. A shared morpheme is one
# row per token, not a duplicated morpheme.
eq(_conn.execute("SELECT COUNT(*) FROM morpheme WHERE node_id=?",
                 (_verse,)).fetchone()[0], 3,
   "a straddling morpheme is stored once, not once per token")
eq(_conn.execute(
    "SELECT COUNT(*) FROM token_morpheme WHERE shared=1").fetchone()[0], 2,
   "...and linked to both tokens it has characters in")
eq(_conn.execute("SELECT COUNT(*) FROM token WHERE node_id=?",
                 (_verse,)).fetchone()[0], 2, "both printed tokens are stored")

# Ordinals are the join key, so a payload cannot silently shift. Reading back the
# alignment must reproduce it exactly.
_payload = store_module.verse_payload(_conn, _verse)
eq([t["t"] for t in _payload["tokens"]], ["పరికరారూఢుం", "డగు"],
   "tokens round-trip in printed order")
eq([m["f"] for m in _payload["tokens"][0]["m"]], ["పరికర", "ఆరూఢుండు"],
   "the first token's morphemes round-trip")
eq([m["f"] for m in _payload["tokens"][1]["m"]], ["ఆరూఢుండు", "అగున్"],
   "the straddling morpheme appears under the second token too")
eq(_payload["paraphrase"], "ఒక భావము", "the verse paraphrase round-trips")
check(_payload["tokens"][0]["m"][1]["s"] == 1,
      "the reader is told the morpheme spans the line break")

# Provenance: a correction supersedes rather than overwrites, so history survives and the
# UI can distinguish a scholar's reading from an inferred one.
_mid = _conn.execute(
    "SELECT id FROM morpheme WHERE node_id=? AND ordinal=0", (_verse,)).fetchone()[0]
_old = _conn.execute(
    "SELECT id FROM gloss WHERE morpheme_id=? AND superseded_by IS NULL",
    (_mid,)).fetchone()[0]
_new = _conn.execute(
    "INSERT INTO gloss (morpheme_id, text, confidence, annotator)"
    " VALUES (?,?,?,?)", (_mid, "సన్నాహము (సరిదిద్దినది)", 0.8, "a scholar")
).lastrowid
_conn.execute("UPDATE gloss SET superseded_by=? WHERE id=?", (_new, _old))
_conn.commit()
eq(_conn.execute(
    "SELECT COUNT(*) FROM gloss WHERE morpheme_id=? AND superseded_by IS NULL",
    (_mid,)).fetchone()[0], 1, "exactly one gloss is live after a correction")
eq(_conn.execute("SELECT COUNT(*) FROM gloss WHERE morpheme_id=?",
                 (_mid,)).fetchone()[0], 2, "...and the superseded one is retained")
eq(store_module.verse_payload(_conn, _verse)["tokens"][0]["m"][0]["g"],
   "సన్నాహము (సరిదిద్దినది)", "the payload serves the live gloss")
check(store_module.verse_payload(_conn, _verse)["tokens"][0]["m"][0]["c"] == 0.8,
      "a non-editorial gloss carries its confidence into the payload")

# The queries that were impossible while HTML was the database.
eq(len(store_module.concordance(_conn, "అగున్")), 1,
   "concordance finds every occurrence of a morpheme")
eq(store_module.senses(_conn, "పరికర")[0]["gloss"], "సన్నాహము (సరిదిద్దినది)",
   "senses reports the live gloss")
check(any(r["urn"] == "w:1.1" for r in store_module.search(_conn, "పరికరారూఢుం")),
      "full-text search finds the verse")

# A duplicated citation must be refused rather than silently double-counted. This is the
# constraint that found 32 verses being counted twice in the real corpus.
try:
    _writer.add_node("verse", parent_id=_book, urn="w:1.1")
    check(False, "a duplicate urn is refused")
except Exception:
    check(True, "a duplicate urn is refused")
_conn.rollback()


# --- Every text has a builder, and the index links to it ------------------
# The bug this guards against: the Vemana analysis was complete — 146 verses, 2,091
# morphemes, validated — and the site showed none of it. There was no builder, nothing
# linked to the page, and the file in `site/` was a leftover from a manual run holding 3
# verses. Every check passed the whole time, because nothing tested that a finished text
# reaches the reader.

from telugu_library import build_all, build_vemana, vemana as vemana_module

_vemana = vemana_module.load()
eq(len(_vemana), 146, "all 146 Vemana verses load")
check(
    all(v.morphemes for v in _vemana),
    "every Vemana verse carries an analysis",
)
eq(
    sum(1 for v in _vemana for m in v.morphemes if not m.is_refrain), 2091,
    "the content morpheme count is what the validator checked",
)

# Each work named in the library index must have an entry pointing somewhere, and each
# builder must be reachable from `build_all` — the two halves of "the reader can find it".
_titles = {title for title, _ in build_all.WORKS}
check("వేమన శతకము" in _titles, "Vemana is listed in the library index")
check("విష్ణు సహస్రనామ స్తోత్రము" in _titles, "the Sahasranāmam is listed")
check("పోతన తెలుగు భాగవతము" in _titles, "the Bhāgavatam is listed")
eq(build_vemana.SLUG, "vemana-satakam", "the Vemana page has a stable slug")

# The renderer returns (html, payload) and must not inline the analysis. Inlining made
# this page 7.3 MB for 146 short verses, because 143 distinct payloads were copied into
# 2,015 word attributes.
_html, _payload = site.render_vemana(_vemana)
check("data-m=" not in _html, "the Vemana page does not inline its analysis")
check('data-payload="' in _html, "...it points at a fetched payload instead")
check(
    len(_html.encode()) < 400_000,
    "the page stays small",
    f"{len(_html.encode()) / 1024:.0f} KB",
)
_parsed = json.loads(_payload)
eq(len(_parsed), 146, "the payload covers every verse")
_referenced = set(re.findall(r'data-v="(\d+)"', _html))
check(
    _referenced and _referenced <= set(_parsed),
    "every clickable word resolves to a payload entry",
)


# --- Report ---------------------------------------------------------------

print()
if failures:
    print(f"{failures} of {checks} checks FAILED")
    sys.exit(1)
print(f"all {checks} checks passed")
