"""Building the Viṣṇu Sahasranāmam.

    python -m telugu_library.build_sahasranamam

Separate from the Bhāgavatam build because the text is a different shape — a numbered list
of a thousand names with explanations, not verse with a morpheme gloss — and pretending one
pipeline fits both would mean fitting neither well.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import site
from .sahasranamam import TITLE, load
from .wikisource import cached_page

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"
SLUG = "vishnu-sahasranamam"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    page = cached_page(TITLE)
    if page is None:
        sys.exit(f"could not fetch {TITLE!r}")

    document = load(page)
    site.write(
        args.out / "text" / f"{SLUG}.html", site.render_sahasranamam(document)
    )

    print(f"built {TITLE}")
    print(f"  {len(document.names):,} names")
    if document.complete:
        print("  complete: all 1,000 present")
    else:
        # Said loudly. Reading only the first of the page's two formats yields 308 names
        # and looks like a clean parse, so silence here would hide two thirds of the text.
        print(f"  INCOMPLETE: {len(document.missing)} missing, e.g. {document.missing[:8]}")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
