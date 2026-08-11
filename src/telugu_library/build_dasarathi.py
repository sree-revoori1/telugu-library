"""Building the Dāśarathī Śatakam.

    python -m telugu_library.build_dasarathi

Shares the śatakam renderer with Vemana and Sumatī.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import site
from .dasarathi import PROVENANCE, SLUG, TITLE, load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    text = load()
    if not text.verses:
        sys.exit("no annotated verses in data/dasarathi/annotated.json")

    document, payload = site.render_satakam(text.verses, TITLE, SLUG, PROVENANCE)
    site.write(args.out / "text" / f"{SLUG}.html", document)
    site.write(args.out / "data" / f"{SLUG}.json", payload)

    print(f"built {TITLE}")
    print(f"  {len(text.verses):,} verses, {text.token_count:,} tokens, "
          f"{text.morpheme_count:,} morphemes")
    print(f"  tokens with no gloss: {len(text.unaligned)}")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
