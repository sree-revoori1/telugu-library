"""Building the Vemana Śatakam.

    python -m telugu_library.build_vemana

Its own entry point, like the Sahasranāmam's, because the text is a different shape from
the Bhāgavatam's: 146 short verses whose analysis is written by hand rather than parsed
from an editorial ṭīka.

This module existed as a renderer and a data file with nothing joining them — the page in
`site/` was left over from a manual run, held 3 verses rather than 146, and no index
linked to it. So the analysis was complete and the site showed none of it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import site
from .vemana import DUPLICATE_PAIRS, TITLE, load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"
SLUG = "vemana-satakam"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    verses = load()
    if not verses:
        sys.exit("no annotated Vemana verses found in data/vemana/annotated.json")

    document, payload = site.render_vemana(verses)
    site.write(args.out / "text" / f"{SLUG}.html", document)
    site.write(args.out / "data" / f"{SLUG}.json", payload)

    morphemes = sum(len(v.morphemes) for v in verses)
    content = sum(1 for v in verses for m in v.morphemes if not m.is_refrain)
    print(f"built {TITLE}")
    print(f"  {len(verses):,} verses, {morphemes:,} morphemes")
    print(f"  {content:,} content morphemes ({morphemes - content:,} refrain)")
    print(f"  {len(DUPLICATE_PAIRS)} verses printed twice in the source, kept at both numbers")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
