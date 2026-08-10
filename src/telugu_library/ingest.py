"""Populating the store from the cached Wikisource pages.

    python -m telugu_library.ingest --all
    python -m telugu_library.ingest --skandham 1 --db /tmp/try.db

This is the seam the project was missing. Before, `align()`'s output went straight into
HTML and existed nowhere else; now it lands in `library.db` and rendering reads from
there. Ingest is a pure function of the page cache, so it is deterministic and cheap to
re-run — which is why `--fresh` rebuilds rather than migrating.

The verse hierarchy is built as corpus → work → skandham → section → verse, and each
verse gets a citable URN (`bhagavatam:1.34`) derived from the text's own numbering so
that references survive a rebuild.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import store
from .bhagavatam import annotate
from .build_bhagavatam import PREFIX, SKANDHAMS, page_list
from .wikisource import LICENCE, LICENCE_URL, cached_page


def ingest_bhagavatam(
    connection, skandhams=None, progress: bool = True
) -> dict:
    """Reads every cached Bhāgavatam page into the store."""
    writer = store.Writer(connection)
    source_id = writer.add_source(
        "wikisource-bhagavatam",
        title="పోతన తెలుగు భాగవతము (Telugu Wikisource)",
        url="https://te.wikisource.org/wiki/పోతన_తెలుగు_భాగవతము",
        licence=LICENCE,
        kind="editorial",
    )

    corpus_id = writer.add_node("corpus", label="తెలుగు గ్రంథాలయం", urn="telugu")
    work_id = writer.add_node(
        "work",
        label="పోతన తెలుగు భాగవతము",
        parent_id=corpus_id,
        urn="bhagavatam",
        meta={"licence": LICENCE, "licence_url": LICENCE_URL},
    )

    pages = page_list()
    wanted = skandhams or SKANDHAMS
    verses = 0
    # Wikisource's section pages overlap: 32 verses appear on two pages apiece with
    # identical text, because a story's boundary is editorial and two sections claim the
    # verses that straddle it (`చాక్షుసమనువుచరిత్ర` and `రైవతమనువుచరిత్ర` share three).
    # A verse is one verse however many pages print it, so the second occurrence is
    # skipped and counted. This is also the arithmetic behind a figure this project has
    # been reporting for weeks: 8,980 distinct verses + 32 repeats = the "9,012" that
    # came out of the old HTML pipeline, which had no way to notice.
    seen_urns: dict[str, int] = {}
    duplicates = 0

    for index, (name, groups) in enumerate(wanted, 1):
        titles = sorted(
            title
            for group in groups
            for title in pages
            if title.startswith(PREFIX + group + "/")
        )
        if not titles:
            continue
        book_id = writer.add_node(
            "book", label=name, parent_id=work_id, ref=str(index),
            urn=f"bhagavatam:{index}",
        )
        for title in titles:
            try:
                page = cached_page(title)
            except Exception:
                continue
            if page is None or not page.text.strip():
                continue
            text = annotate(page)
            if not text.verses:
                continue  # a table of contents, not a verse page
            section_id = writer.add_node(
                "section",
                label=title.split("/")[-1],
                parent_id=book_id,
                meta={"url": page.url, "revision": page.revision, "title": title},
            )
            for verse in text.verses:
                # The source's own numbering, so the reference is citable and stable.
                urn = f"bhagavatam:{verse.skandham}.{verse.number}"
                if urn in seen_urns:
                    duplicates += 1
                    continue
                seen_urns[urn] = 1
                writer.add_verse(
                    section_id,
                    urn=urn,
                    ref=verse.reference,
                    alignment=verse.alignment,
                    morphemes=verse.morphemes,
                    lines=[l.split() for l in verse.text.split("\n") if l.split()],
                    paraphrase=verse.paraphrase,
                    metre_code=verse.metre,
                    metre_name=verse.metre_name,
                    source_id=source_id,
                    confidence=1.0,  # a scholar wrote it
                )
                verses += 1
        connection.commit()
        if progress:
            print(f"  {name}: {len(titles)} pages, {verses:,} verses so far", flush=True)

    connection.commit()
    stats = store.statistics(connection)
    stats["duplicate_verses_skipped"] = duplicates
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--skandham", type=int, default=None, help="1-based")
    parser.add_argument("--db", type=Path, default=store.DEFAULT_DB)
    parser.add_argument(
        "--fresh", action="store_true", default=True,
        help="rebuild from scratch (the default; ingest is deterministic)",
    )
    args = parser.parse_args(argv)

    skandhams = None
    if args.skandham and not args.all:
        skandhams = [SKANDHAMS[args.skandham - 1]]

    connection = store.connect(args.db, fresh=args.fresh)
    stats = ingest_bhagavatam(connection, skandhams)

    print(f"\n{args.db}")
    for key, value in stats.items():
        print(f"  {key:16s} {value:>10,}")
    size = Path(args.db).stat().st_size
    print(f"  {'file size':16s} {size/1048576:>9.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
