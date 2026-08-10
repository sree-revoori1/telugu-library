"""Building the site from the store.

    python -m telugu_library.build_from_store              # render data/library.db
    python -m telugu_library.build_from_store --ingest     # ingest first, then render

The pipeline is now three separable stages rather than one:

    wikisource cache → ingest → library.db → render → site/

Separable is the point. Re-rendering does not re-parse; correcting a gloss does not
re-render the corpus; and the analysis is a file with a URL rather than markup, so
serving an API needs no new code.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import render, site, store
from .ingest import ingest_bhagavatam

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=store.DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--ingest", action="store_true", help="rebuild the store from the page cache"
    )
    args = parser.parse_args(argv)

    if args.ingest or not args.db.exists():
        print("ingesting…", flush=True)
        connection = store.connect(args.db, fresh=True)
        stats = ingest_bhagavatam(connection)
        for key, value in stats.items():
            print(f"  {key:26s} {value:>10,}")
    else:
        connection = store.connect(args.db)

    print("rendering…", flush=True)
    result = render.render_all(connection, args.out)

    # The index, from the store's own hierarchy rather than a parallel list.
    books = connection.execute(
        "SELECT id, label FROM node WHERE kind = 'book' ORDER BY path"
    ).fetchall()
    ordered: dict[str, list] = {}
    for book in books:
        sections = connection.execute(
            "SELECT id, label FROM node WHERE parent_id = ? AND kind = 'section'"
            " ORDER BY path",
            (book["id"],),
        ).fetchall()
        entries = [(s["label"], f"s{s['id']:05d}") for s in sections]
        if entries:
            ordered[book["label"]] = entries
            site.write(
                args.out / "genre" / f"{book['label']}.html",
                site.render_genre(book["label"], entries),
            )
    site.write(
        args.out / "index.html",
        site.render_index(
            ordered,
            {name: f"{len(e):,} sections" for name, e in ordered.items()},
        ),
    )

    print(f"\n  sections   {result['sections']:,}")
    print(f"  html       {result['html_mb']:.1f} MB "
          f"(mean {result['mean_page_kb']:.0f} KB/page)")
    print(f"  payloads   {result['payload_mb']:.1f} MB, fetched on demand")
    print(f"  written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
