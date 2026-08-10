"""Building the whole library: every annotated text, and the index over them.

    python -m telugu_library.build_all

Each text has its own builder, because each has its own structure — the Bhāgavatam is verse
with a morpheme gloss, the Sahasranāmam a numbered list of names. This runs them all and
writes the one index that ties them together, so adding a text means adding a builder and a
line here rather than generalising a pipeline that fits nothing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import site
from . import build_bhagavatam, build_from_store, build_sahasranamam, build_vemana

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"

# The works in the library, in the order a reader should meet them.
WORKS = [
    (
        "పోతన తెలుగు భాగవతము",
        "Pothana's Bhāgavatam — 12 skandhams, verse by verse, "
        "with the editorial word-by-word gloss",
    ),
    (
        "విష్ణు సహస్రనామ స్తోత్రము",
        "The thousand names of Viṣṇu, each with its Telugu explanation",
    ),
    (
        "వేమన శతకము",
        "Vemana's 146 verses, analysed word by word — this project's own gloss, "
        "since no published ṭīka of Vemana exists",
    ),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--inline",
        action="store_true",
        help="use the older renderer that inlines the analysis into the markup",
    )
    args = parser.parse_args(argv)

    print("=== Bhāgavatam")
    if args.inline:
        build_bhagavatam.main(["--all", "--out", str(args.out)])
    else:
        # Through the store: ingest once, then render from it. Slower on a cold cache by
        # the cost of one ingest, and far faster for everything afterwards — re-rendering
        # takes ~3 s against ~5 min to re-parse, and the pages come out at 41 KB rather
        # than 141 KB because the analysis is fetched instead of inlined.
        build_from_store.main(["--out", str(args.out), "--ingest"])
    print("\n=== Sahasranāmam")
    build_sahasranamam.main(["--out", str(args.out)])
    print("\n=== Vemana")
    build_vemana.main(["--out", str(args.out)])

    # The library index, over works rather than over the Bhāgavatam's skandhams. The
    # Bhāgavatam's own contents page is written by its builder.
    entries = {
        "పోతన తెలుగు భాగవతము": [("12 skandhams", "../genre/ప్రథమ స్కంధము")],
        "విష్ణు సహస్రనామ స్తోత్రము": [
            ("1,000 names", "../text/vishnu-sahasranamam")
        ],
        "వేమన శతకము": [("146 verses", "../text/vemana-satakam")],
    }
    site.write(
        args.out / "index.html",
        site.render_library(WORKS, entries),
    )
    print(f"\nlibrary index written to {args.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
