"""Building the Sumatī Śatakam.

    python -m telugu_library.build_sumati

Shares Vemana's renderer, since the two texts are the same shape — 100-odd short verses
with a hand-written morpheme gloss and no editorial ṭīka to quote.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import site
from .sumati import TITLE, load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"
SLUG = "sumati-satakam"

PROVENANCE = (
    "the word-by-word analysis here is this project's own, not a scholar's — "
    "no published ప్రతిపదార్థము of the Sumatī Śatakam exists online"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    verses = load()
    if not verses:
        sys.exit("no annotated verses in data/sumati/annotated.json")

    document, payload = site.render_satakam(verses, TITLE, SLUG, PROVENANCE)
    site.write(args.out / "text" / f"{SLUG}.html", document)
    site.write(args.out / "data" / f"{SLUG}.json", payload)

    tokens = sum(len(v.alignment) for v in verses)
    morphemes = sum(len(v.morphemes) for v in verses)
    orphans = sum(1 for v in verses for _, _, ms in v.alignment if not ms)
    print(f"built {TITLE}")
    print(f"  {len(verses):,} verses, {tokens:,} tokens, {morphemes:,} morphemes")
    print(f"  tokens with no gloss: {orphans}")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
