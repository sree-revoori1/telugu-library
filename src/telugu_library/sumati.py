"""The Sumatī Śatakam, with a word-by-word analysis written for this library.

Attributed to Baddena (13th century), and the one Telugu text nearly every schoolchild
still learns by heart. 108 verses of practical ethics in *kanda padyam*, each closing with
the vocative `సుమతీ` — "O wise one" — which is the poet's address to the reader rather than
a signature.

Like Vemana and unlike the Bhāgavatam, no editorial ṭīka exists for it online, so the
analysis here is *made* rather than quoted, and the page says so. The shape deliberately
matches Vemana's: verses with lines, a flat morpheme list in reading order, and the shared
character-stream aligner mapping morphemes onto printed tokens.

One structural difference from Vemana worth knowing. Vemana's refrain is four words long
(`విశ్వదాభిరామ వినుర వేమ`) and identical everywhere, so it is glossed once and skipped by
the validator. Sumatī's is the single word `సుమతీ`, which is part of the verse's own
grammar — the vocative that the sentence addresses — so it is glossed like any other word.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .alignment import AKSHARAM, align_streams, shared_indices

DATA = Path(__file__).resolve().parents[2] / "data" / "sumati" / "annotated.json"

TITLE = "సుమతీ శతకము"

# The vocative that closes every verse. Unlike Vemana's four-word refrain this is one word
# and part of the sentence, so it is glossed rather than set aside.
REFRAIN_WORDS = frozenset({"సుమతీ"})


@dataclass
class Morpheme:
    form: str
    gloss: str
    shared: bool = False

    @property
    def is_refrain(self) -> bool:
        return self.form in REFRAIN_WORDS


@dataclass
class Verse:
    number: int
    lines: list[str]
    morphemes: list[Morpheme] = field(default_factory=list)
    alignment: list = field(default_factory=list)

    @property
    def reference(self) -> str:
        return str(self.number)

    @property
    def text(self) -> str:
        return " ".join(self.lines)


def align(verse: Verse) -> list[tuple[int, str, list[Morpheme]]]:
    """Each printed token mapped to the morphemes inside it, keeping the lineation."""
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


def load(path: Path = DATA) -> list[Verse]:
    """The annotated verses, in order, aligned."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    verses = []
    for key in sorted(raw, key=int):
        entry = raw[key]
        verses.append(
            Verse(
                number=int(key),
                lines=entry["lines"],
                morphemes=[Morpheme(form=f, gloss=g) for f, g in entry["gloss"]],
            )
        )
    for verse in verses:
        verse.alignment = align(verse)
    return verses
