"""Śatakams: 100-odd short verses with a hand-written word-by-word analysis.

Three texts now share this shape — Vemana, Sumatī, Dāśarathī — so the loading, the
alignment and the refrain handling live here once rather than in three near-identical
modules. What differs between them is data, not code:

    title           what to head the page with
    slug            the page and payload filename
    refrain         the words that close every verse
    provenance      what to tell the reader about where the gloss came from

The refrain differs in kind between them, which is why it is a parameter and not a
constant. Vemana's `విశ్వదాభిరామ వినుర వేమ` is four fixed words carrying no sentence role,
so it is glossed once and set aside. Sumatī's `సుమతీ` is a single vocative that the sentence
grammatically addresses. Dāśarathī's `దాశరథీ కరుణాపయోనిధీ` is two vocatives, both compounds
that need splitting — `కరుణా` + `పయోనిధీ`, "ocean of compassion".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .alignment import AKSHARAM, align_streams, shared_indices

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


@dataclass
class Morpheme:
    form: str
    gloss: str
    # True when this morpheme has characters in more than one printed token, so it is
    # listed under both. Classical printing breaks on the metre, not the word.
    shared: bool = False
    refrain: bool = False

    @property
    def is_refrain(self) -> bool:
        return self.refrain


@dataclass
class Verse:
    number: int
    lines: list[str]
    morphemes: list[Morpheme] = field(default_factory=list)
    # (line index, printed token, [Morpheme]) so the poet's lineation survives.
    alignment: list = field(default_factory=list)

    @property
    def reference(self) -> str:
        return str(self.number)

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass
class Satakam:
    """One śatakam: its identity and its verses."""

    name: str
    title: str
    slug: str
    provenance: str
    refrain: frozenset
    verses: list[Verse] = field(default_factory=list)

    @property
    def morpheme_count(self) -> int:
        return sum(len(v.morphemes) for v in self.verses)

    @property
    def token_count(self) -> int:
        return sum(len(v.alignment) for v in self.verses)

    @property
    def unaligned(self) -> list[tuple[int, str]]:
        """Printed tokens no gloss accounts for.

        The question a gloss-only validator cannot ask. Vemana had one of these for weeks
        while its checker reported a clean run.
        """
        return [
            (v.number, token)
            for v in self.verses
            for _, token, morphemes in v.alignment
            if not morphemes
        ]


def align(verse: Verse) -> list[tuple[int, str, list[Morpheme]]]:
    """Each printed token mapped to the morphemes inside it, keeping the lineation.

    Words routinely split across the line end in these metres — Dāśarathī sets `శృంగార` as
    `…శృం` / `గార…` — so a morpheme may belong to two tokens. The character-stream aligner
    in `alignment` represents that directly; see its docstring for why three approaches
    that counted units instead failed.
    """
    tokens: list[str] = []
    line_of: list[int] = []
    for index, line in enumerate(verse.lines):
        for token in line.split():
            if AKSHARAM.search(token):
                tokens.append(token)
                line_of.append(index)
    if not tokens or not verse.morphemes:
        return [(line_of[i], t, []) for i, t in enumerate(tokens)]

    by_token = align_streams(tokens, [m.form for m in verse.morphemes])
    for index in shared_indices(by_token):
        verse.morphemes[index].shared = True

    return [
        (line_of[i], token, [verse.morphemes[j] for j in by_token[i]])
        for i, token in enumerate(tokens)
    ]


def load(
    name: str,
    title: str,
    slug: str,
    provenance: str,
    refrain: frozenset,
) -> Satakam:
    """One śatakam, read from `data/<name>/annotated.json` and aligned."""
    path = DATA_ROOT / name / "annotated.json"
    if not path.exists():
        return Satakam(name, title, slug, provenance, refrain)
    raw = json.loads(path.read_text(encoding="utf-8"))
    verses = []
    for key in sorted(raw, key=int):
        entry = raw[key]
        verses.append(
            Verse(
                number=int(key),
                lines=entry["lines"],
                morphemes=[
                    Morpheme(form=f, gloss=g, refrain=f in refrain)
                    for f, g in entry["gloss"]
                ],
            )
        )
    for verse in verses:
        verse.alignment = align(verse)
    return Satakam(name, title, slug, provenance, refrain, verses)
