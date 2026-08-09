"""Parsing the Viṣṇu Sahasranāmam, a thousand names with their explanations.

A different shape of text from the Bhāgavatam, and simpler to annotate. There is no verse
to align: the source is a numbered list, one name per line with a Telugu explanation of
what the name means. So each name is already its own unit and the alignment problem does
not arise at all.

What does need care is that the page is not written in one format. Two conventions appear,
by different contributors, and they overlap:

    1.విశ్వం --- విశ్వము అంతా తానే ఐన వాడు …      names 1–308
    301) యుగావర్త: - యుగములను త్రిప్పువాడు.        names 301–1000

Between 301 and 308 both are present, so the same name appears twice with two different
explanations. Reading only one format loses two thirds of the text; reading both naively
duplicates eight names. Both formats are read and the numbers deduplicated, keeping the
first explanation and recording the second as an alternative, since two scholars glossing a
name differently is information rather than a conflict.

The names themselves are Sanskrit, written in Telugu script, and many are compounds:
`భూతభవ్యభవత్ ప్రభుః` is "lord of past, present and future". Splitting those is where a
reader most needs help, and it is the one thing the source does not do — so unlike the
Bhāgavatam, the compound analysis here has to come from elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TITLE = "విష్ణు సహస్రనామ స్తోత్రము"

# `1.విశ్వం --- explanation`. The name runs to the dashes, so it may contain spaces —
# `భూతభవ్యభవత్ ప్రభుః` is one name of two words.
FORMAT_A = re.compile(r"^\s*(\d+)\s*\.\s*([^-]+?)\s*-{2,}\s*(.+)$")

# `301) యుగావర్త: - explanation`. The separator is a single dash or colon, which means the
# name's own trailing visarga has to be handled: `యుగావర్త:` ends in one.
FORMAT_B = re.compile(r"^\s*(\d+)\s*\)\s*(.+?)\s*[-–]\s*(.+)$")


@dataclass
class Name:
    """One of the thousand names."""

    number: int
    name: str
    # The editor's Telugu explanation, quoted rather than rewritten.
    meaning: str
    # A second explanation where the two formats overlap, or a contributor gave one.
    alternatives: list[str] = field(default_factory=list)

    @property
    def words(self) -> list[str]:
        """The name split on whitespace, which is as far as the source goes."""
        return [w for w in self.name.split() if w]


def _clean_name(text: str) -> str:
    """A name with the punctuation the source varies on removed.

    Sanskrit visarga is written `:` in these lines — `యుగావర్త:` — and is part of the name
    rather than punctuation, so it is kept. A trailing full stop or comma is not.
    """
    return text.strip().strip(".,;")


def parse(text: str) -> list[Name]:
    """Every name, in order, reading both formats and merging the overlap."""
    found: dict[int, Name] = {}
    order: list[int] = []

    for line in text.splitlines():
        for pattern in (FORMAT_A, FORMAT_B):
            match = pattern.match(line)
            if not match:
                continue
            number = int(match.group(1))
            name = _clean_name(match.group(2))
            meaning = " ".join(match.group(3).split()).strip()
            if not name or not meaning:
                break
            if number in found:
                # The formats overlap at 301–308. Two glosses of one name is extra
                # evidence, not a clash, so the second is kept as an alternative.
                existing = found[number]
                if meaning != existing.meaning and meaning not in existing.alternatives:
                    existing.alternatives.append(meaning)
            else:
                found[number] = Name(number=number, name=name, meaning=meaning)
                order.append(number)
            break

    return [found[n] for n in sorted(order)]


@dataclass
class Sahasranamam:
    """The thousand names, ready to render."""

    names: list[Name]
    url: str = ""
    revision: int = 0
    title: str = TITLE

    @property
    def complete(self) -> bool:
        """Whether all thousand names are present.

        Worth asserting rather than assuming: reading only the first format yields 308 of
        1,000 and looks like a successful parse.
        """
        return {n.number for n in self.names} == set(range(1, 1001))

    @property
    def missing(self) -> list[int]:
        return sorted(set(range(1, 1001)) - {n.number for n in self.names})


def load(page) -> Sahasranamam:
    return Sahasranamam(
        names=parse(page.text), url=page.url, revision=page.revision,
        title=page.title,
    )
