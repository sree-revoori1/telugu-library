"""Building the site: fetch, parse, render.

    python -m telugu_library.build            # a sample, for checking the layout
    python -m telugu_library.build --all      # the whole catalogue

Deliberately resumable. The catalogue is 4,842 texts, fetching is rate-limited out of
courtesy to a donated service, and a build that has to start over after an interruption
would never finish. Every page is cached on disk, so a second run costs nothing.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from . import site
from .catalogue import GENRES, build as build_catalogue, load, save
from .reader import parse
from .wikisource import cached_page

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "site"


def _analyser():
    """The analyser, in classical mode.

    Classical mode is on because the corpus is classical: it folds the arasunna, which
    modern Telugu has dropped and which appears in 12.5% of classical tokens. Without it
    nearly every word misses the lexicon by one codepoint.
    """
    try:
        from telugu_morph.layered import LayeredAnalyser
        from telugu_morph.lexicon import load_lexicon
    except ImportError:  # pragma: no cover
        sys.exit(
            "telugu-morph is required.\n"
            "  pip install git+https://github.com/sree-revoori1/telugu-morph"
        )
    lexicon = load_lexicon()
    return LayeredAnalyser(lexicon, classical=True), lexicon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="build every text")
    parser.add_argument(
        "--limit", type=int, default=40, help="texts per genre when sampling"
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)

    catalogue_path = DATA / "catalogue.json"
    if catalogue_path.exists():
        works = load(catalogue_path)
    else:
        print("building the catalogue…", flush=True)
        works = build_catalogue()
        save(works, catalogue_path)
    print(f"catalogue: {len(works):,} texts", flush=True)

    by_genre: dict[str, list] = defaultdict(list)
    for work in works:
        by_genre[work.genre].append(work)

    if not args.all:
        # A sample large enough to judge the layout and the coverage claim, small
        # enough to build in a minute.
        by_genre = {
            genre: entries[: args.limit] for genre, entries in by_genre.items()
        }

    analyser, lexicon = _analyser()
    rendered: dict[str, list[tuple[str, str]]] = defaultdict(list)
    total_tokens = analysed_tokens = 0
    skipped = 0

    for genre, entries in by_genre.items():
        for index, work in enumerate(entries, 1):
            page = cached_page(work.title)
            if page is None or not page.text.strip():
                skipped += 1
                continue
            document = parse(
                work.title,
                page.text,
                analyser,
                url=page.url,
                revision=page.revision,
                genre=genre,
                path=work.path,
                lexicon=lexicon,
            )
            if document.token_count < 5:
                # A stub or a redirect, not a text.
                skipped += 1
                continue
            site.write(
                args.out / "text" / f"{work.slug}.html",
                site.render_document(document),
            )
            rendered[genre].append((work.title, work.slug))
            total_tokens += document.token_count
            analysed_tokens += document.analysed_count
            if index % 25 == 0:
                print(f"  {genre}: {index}/{len(entries)}", flush=True)

    for genre, entries in rendered.items():
        site.write(
            args.out / "genre" / f"{genre}.html", site.render_genre(genre, entries)
        )
    site.write(
        args.out / "index.html", site.render_index(dict(rendered), GENRES)
    )

    coverage = 100.0 * analysed_tokens / total_tokens if total_tokens else 0.0
    print(
        f"\nbuilt {sum(len(e) for e in rendered.values()):,} texts"
        f" ({skipped:,} skipped as stubs)"
    )
    print(f"  {total_tokens:,} Telugu words, {coverage:.1f}% with a gloss")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
