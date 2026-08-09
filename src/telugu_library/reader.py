"""Turning a fetched text into a parsed, readable document.

This is the layer that makes the library a *parsing reader* rather than a collection of
files. Every Telugu token gets its lemma, morphological tag and part of speech attached
at build time, so the site needs no server and no JavaScript beyond showing a panel.

Three things the naive approach gets wrong, all of which the corpus forced.

**Verse must stay verse.** A Telugu poem is laid out in metrical lines and a padyam is
a unit; reflowing it as prose destroys the form the poet wrote in. Line breaks are
preserved and the verse markers (`కం.`, `వ.`) are recognised so the reader can style a
padyam differently from a prose passage.

**A token is not a word.** Classical verse writes sandhi across the word boundary and
breaks lines on the metrical foot, so `పురుషుండు ఆఢ్యుఁడు` is printed `పురుషుం
డాఢ్యుఁడు` — the printed token is the tail of one word plus the head of the next.
Where an analysis fails, the reader says so rather than guessing, because a confident
wrong gloss on a scriptural text is worse than an honest gap.

**Punctuation and numerals are not Telugu words.** The verse numbers `(1-185)` are
navigation, not vocabulary, and must not be sent to the analyser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .language import language_of

# A run of Telugu *letters*. Everything else — spaces, punctuation, the Latin text of
# an editorial note — is passed through untouched.
#
# The range deliberately excludes U+0C66–U+0C6F, the Telugu digits ౦౧౨౩౪౫౬౭౮౯. A
# naive `[ఀ-౿]` includes them, so every verse number written in Telugu numerals was
# sent to the analyser as if it were a word. In the Vālmīki Rāmāyaṇam that is a large
# share of all tokens — `౩`, `౬౪`, `౨` were among the commonest "unanalysed words" —
# and counting them as failures understated coverage badly.
TELUGU_RUN = re.compile(r"[\u0C00-\u0C65\u0C70-\u0C7F]+")

# Verse-form markers, which open a line and name its metre. Recognised so the reader can
# lay out a padyam as a padyam.
VERSE_MARKERS: tuple[str, ...] = (
    "కం.", "క.", "వ.", "సీ.", "ఆ.", "తే.", "మ.", "శా.", "ఉ.", "చ.", "గీ.",
    "ద్వి.", "ఉత్సాహ.", "మత్త.",
)

VERSE_NUMBER = re.compile(r"\(\s*\d+\s*-\s*\d+\s*\)")


@dataclass
class Token:
    """One token of a text, with its analysis if there is one."""

    surface: str
    # None for punctuation and anything not Telugu.
    lemma: str | None = None
    tag: str | None = None
    pos: str | None = None
    # True when the analyser had nothing to say. Recorded rather than hidden, because
    # the gap is information: it usually means a sandhi-split token.
    unanalysed: bool = False
    # Other readings, for a word that is genuinely ambiguous out of context.
    alternatives: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_telugu(self) -> bool:
        return bool(TELUGU_RUN.fullmatch(self.surface))


@dataclass
class Line:
    """One line of a text, which for verse is one metrical line."""

    tokens: list[Token]
    # The verse marker that opened this line, if any: `కం.` and so on.
    marker: str | None = None
    # The canonical verse number this line carries, e.g. `1-185`.
    verse: str | None = None

    @property
    def text(self) -> str:
        return "".join(t.surface for t in self.tokens)

    @property
    def is_blank(self) -> bool:
        return not self.text.strip()


@dataclass
class Document:
    """A whole parsed text, ready to render."""

    title: str
    lines: list[Line]
    url: str = ""
    revision: int = 0
    genre: str = ""
    path: list[str] = field(default_factory=list)
    # "telugu" or "sanskrit". A large part of Wikisource's epic category is the Vālmīki
    # Rāmāyaṇam, which is Sanskrit in Telugu script — see `language.py`. Recorded so the
    # page can say so and so coverage is not averaged across two languages.
    language: str = "telugu"

    @property
    def token_count(self) -> int:
        return sum(1 for line in self.lines for t in line.tokens if t.is_telugu)

    @property
    def analysed_count(self) -> int:
        return sum(
            1
            for line in self.lines
            for t in line.tokens
            if t.is_telugu and not t.unanalysed
        )

    @property
    def coverage(self) -> float:
        """The share of Telugu tokens that got an analysis.

        Reported on every page. A reader deserves to know how much of what they are
        looking at is glossed, especially given that classical text runs near 50% —
        presenting a half-parsed page as if it were fully parsed would be misleading.
        """
        total = self.token_count
        return 100.0 * self.analysed_count / total if total else 0.0


def _split_line(text: str) -> list[str]:
    """A line into Telugu runs and everything between them, in order."""
    parts: list[str] = []
    position = 0
    for match in TELUGU_RUN.finditer(text):
        if match.start() > position:
            parts.append(text[position : match.start()])
        parts.append(match.group())
        position = match.end()
    if position < len(text):
        parts.append(text[position:])
    return parts


def _marker_of(text: str) -> str | None:
    stripped = text.lstrip()
    for marker in VERSE_MARKERS:
        if stripped.startswith(marker):
            return marker
    return None


def parse(
    title: str,
    text: str,
    analyser,
    url: str = "",
    revision: int = 0,
    genre: str = "",
    path: list[str] | None = None,
    max_alternatives: int = 3,
    lexicon: dict | None = None,
) -> Document:
    """Parses a text into a document with every Telugu token analysed.

    `analyser` is a `telugu_morph.LayeredAnalyser`, which the caller constructs with
    `classical=True` for a classical text. Passing it in rather than building it here
    keeps the analysis cache warm across a whole corpus — the same words recur
    constantly, and rebuilding per document made the site build minutes slower.

    `lexicon` is used to check that a proposed lemma is a real word. Without it every
    parse is reported as a success, including the fragments that classical
    line-breaking produces.
    """
    lexicon = lexicon if lexicon is not None else getattr(analyser, "lexicon", None)
    # Sanskrit is not glossed at all. A Telugu analyser applied to Sanskrit does not
    # fail cleanly — it produces confident nonsense, reading the locative `సూర్యే` as a
    # participle of an invented verb `సూర్యు` — and a wrong gloss on a scriptural line
    # is worse than none.
    language = language_of(text)
    gloss = language == "telugu"
    lines: list[Line] = []
    for raw in text.splitlines():
        verse_match = VERSE_NUMBER.search(raw)
        tokens: list[Token] = []
        for part in _split_line(raw):
            token = Token(surface=part)
            if token.is_telugu and not gloss:
                token.unanalysed = True
            elif token.is_telugu:
                readings = analyser.analyse(part, max_results=max_alternatives)
                if readings:
                    best = readings[0]
                    token.lemma = best.lemma
                    token.tag = best.tag
                    token.pos = best.pos
                    # A gloss counts only if it found a *word*. Two ways it can fail,
                    # and both were reporting as success:
                    #
                    #   * the reading merely repeats the input, explaining nothing;
                    #   * the "lemma" is a fragment the corpus has never seen.
                    #
                    # The second is the one that matters on classical text, because a
                    # sandhi-split token still parses. `డాఢ్యుఁడు` is the tail of
                    # `పురుషుండు` plus the head of `ఆఢ్యుఁడు`, and it happily analysed
                    # to `డాఢ్యుడు` — zero occurrences in 33 million words. Presenting
                    # that to a reader as the lemma of a scriptural line is worse than
                    # admitting the gap.
                    #
                    # Verb citation forms are exempt, since Telugu barely writes them:
                    # `పరిశీలించు` occurs zero times against 205 for its inflections.
                    # The one test that matters: is the proposed lemma a word?
                    #
                    # An earlier version also required the reading to have *steps* —
                    # some suffix peeled off — and that was simply wrong. Most Telugu
                    # tokens in running text are uninflected, so `ఈ` (this, 294,297
                    # occurrences), `మీ` (your, 148,590) and `తన` (own, 111,810)
                    # analyse to themselves with no steps, which is the correct answer.
                    # Marking them unanalysed made the commonest words in the language
                    # look like failures and understated coverage badly.
                    #
                    # A fragment is excluded by the attestation test alone:
                    # `డాఢ్యుఁడు` yields the "lemma" `డాఢ్యుడు`, which occurs zero
                    # times in 33 million words.
                    #
                    # Verb citation forms are exempt, since Telugu barely writes them:
                    # `పరిశీలించు` occurs zero times against 205 for its inflections.
                    attested = bool(lexicon.get(best.lemma, 0)) if lexicon else True
                    productive = best.pos == "verb" and best.lemma.endswith("ు")
                    token.unanalysed = not (attested or productive)
                    token.alternatives = [
                        (r.lemma, r.tag)
                        for r in readings[1:]
                        if r.lemma != best.lemma
                    ]
                else:
                    token.unanalysed = True
            tokens.append(token)
        lines.append(
            Line(
                tokens=tokens,
                marker=_marker_of(raw),
                verse=verse_match.group().strip("() ") if verse_match else None,
            )
        )
    return Document(
        title=title,
        lines=lines,
        url=url,
        revision=revision,
        genre=genre,
        path=path or [],
        language=language,
    )
