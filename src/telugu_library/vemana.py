"""Vemana's Śatakam, with a word-by-word analysis written for this library.

Unlike the Bhāgavatam, no editorial gloss exists for Vemana anywhere online. Telugu
Wikisource has 791 first lines used as page titles and only 6 with any body text; the
verses themselves were never transcribed there. So the analysis here is *made* rather
than parsed, and that difference is stated on the page rather than hidden — a reader
should know whether a gloss carries a scholar's authority or this project's.

The shape is deliberately the same as the Bhāgavatam's, so the reader learns one
interface: each verse has its lines, and a list of morphemes paired with a modern Telugu
meaning, sandhi resolved and compounds split.

Vemana wrote in the 16th century and the text is long out of copyright. Each verse closes
with the refrain `విశ్వదాభిరామ వినుర వేమ` — "O Vema, pleasing to the universe, listen" —
which is the poet's signature and is glossed once rather than argued over.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "vemana" / "annotated.json"

TITLE = "వేమన శతకము"

# The closing refrain, present in almost every verse. Recognised so the reader is not
# shown the same four glosses a hundred times as though they were new.
REFRAIN_WORDS = frozenset({"విశ్వద", "అభిరామ", "వినుర", "వేమ"})

# The source prints 146 verses but only 141 distinct ones: five are set twice, with
# identical text. Both numbers are kept, because a reader following a citation wants the
# verse at the number they were given, and the repetition is the source's rather than ours.
DUPLICATE_PAIRS = ((31, 41), (37, 40), (45, 62), (76, 87), (80, 90))


@dataclass
class Morpheme:
    form: str
    gloss: str

    @property
    def is_refrain(self) -> bool:
        return self.form in REFRAIN_WORDS


@dataclass
class Verse:
    number: int
    lines: list[str]
    morphemes: list[Morpheme] = field(default_factory=list)

    @property
    def reference(self) -> str:
        return str(self.number)

    @property
    def text(self) -> str:
        return " ".join(self.lines)


def load(path: Path = DATA) -> list[Verse]:
    """The annotated verses, in order."""
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
    return verses
